# -*- coding: utf-8 -*-
"""
===================================
分析服务层
===================================

职责：
1. 封装股票分析逻辑
2. 调用 analyzer 和 pipeline 执行分析
3. 保存分析结果到数据库
"""

import logging
import uuid
from typing import Optional, Dict, Any, Callable
import numpy as np

from src.repositories.analysis_repo import AnalysisRepository
from src.report_language import (
    get_sentiment_label,
    get_localized_stock_name,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    分析服务
    
    封装股票分析相关的业务逻辑
    """
    
    def __init__(self):
        """初始化分析服务"""
        self.repo = AnalysisRepository()
        self.last_error: Optional[str] = None
        self._timesfm_service = None
    
    def analyze_stock(
        self,
        stock_code: str,
        report_type: str = "detailed",
        force_refresh: bool = False,
        query_id: Optional[str] = None,
        send_notification: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        执行股票分析
        
        Args:
            stock_code: 股票代码
            report_type: 报告类型 (simple/detailed)
            force_refresh: 是否强制刷新
            query_id: 查询 ID（可选）
            send_notification: 是否发送通知（API 触发默认发送）
            
        Returns:
            分析结果字典，包含:
            - stock_code: 股票代码
            - stock_name: 股票名称
            - report: 分析报告
        """
        try:
            self.last_error = None
            # 导入分析相关模块
            from src.config import get_config
            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            
            # 生成 query_id
            if query_id is None:
                query_id = uuid.uuid4().hex
            
            # 获取配置
            config = get_config()
            
            # 创建分析流水线
            pipeline = StockAnalysisPipeline(
                config=config,
                query_id=query_id,
                query_source="api",
                progress_callback=progress_callback,
            )
            
            # 确定报告类型 (API: simple/detailed/full/brief -> ReportType)
            rt = ReportType.from_str(report_type)
            
            # 执行分析
            result = pipeline.process_single_stock(
                code=stock_code,
                skip_analysis=False,
                single_stock_notify=send_notification,
                report_type=rt,
            )
            
            if result is None:
                logger.warning(f"分析股票 {stock_code} 返回空结果")
                self.last_error = self.last_error or f"分析股票 {stock_code} 返回空结果"
                return None

            if not getattr(result, "success", True):
                self.last_error = getattr(result, "error_message", None) or f"分析股票 {stock_code} 失败"
                logger.warning(f"分析股票 {stock_code} 未成功完成: {self.last_error}")
                return None
            
            # 构建响应
            return self._build_analysis_response(result, query_id, report_type=rt.value)
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"分析股票 {stock_code} 失败: {e}", exc_info=True)
            return None

    def _run_timesfm_forecast(
        self,
        stock_code: str,
        stock_name: str,
        historical_prices: list,
        historical_volumes: Optional[list] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        运行 TimesFM 预测（支持集成预测）

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            historical_prices: 历史收盘价列表
            historical_volumes: 历史成交量列表（可选，用于协变量特征）

        Returns:
            预测结果字典，失败时返回 None
        """
        try:
            from src.config import get_config
            from src.services.timesfm_service import TimesFMService

            config = get_config()

            # 检查是否启用 TimesFM
            if not getattr(config, 'timesfm_enabled', False):
                logger.debug("TimesFM prediction disabled")
                return None

            # 准备预测参数
            max_context = getattr(config, 'timesfm_max_context', 0)
            max_horizon = getattr(config, 'timesfm_max_horizon', 60)
            device = getattr(config, 'timesfm_device', 'auto')

            # 检查是否启用集成预测
            ensemble_enabled = getattr(config, 'timesfm_ensemble_enabled', False)

            # 如果启用集成，使用集成服务
            if ensemble_enabled:
                return self._run_ensemble_forecast(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    historical_prices=historical_prices,
                    max_context=max_context,
                    max_horizon=max_horizon,
                    device=device,
                )

            # 检查是否启用协变量
            covariates_enabled = getattr(config, 'timesfm_covariates_enabled', False)
            covariate_features_str = getattr(config, 'timesfm_covariate_features', 'volume_change,ma_deviation')
            covariate_features = [f.strip() for f in covariate_features_str.split(',') if f.strip()]

            # 懒加载 TimesFM 服务
            if self._timesfm_service is None:
                self._timesfm_service = TimesFMService(
                    context_len=max_context if max_context > 0 else 256,
                    horizon_len=max_horizon,
                    backend=device if device != 'auto' else 'cpu',
                )

            # 执行预测
            import numpy as np
            prices_array = np.array(historical_prices, dtype=np.float64)

            # 准备成交量数据（如果提供）
            volumes_array = None
            if historical_volumes:
                volumes_array = np.array(historical_volumes, dtype=np.float64)

            # 如果启用协变量，构建协变量矩阵
            if covariates_enabled and covariate_features:
                try:
                    from src.services.forecast_covariate_builder import ForecastCovariateBuilder

                    # 创建协变量构建器
                    covariate_builder = ForecastCovariateBuilder(
                        enabled_features=covariate_features,
                    )

                    # 构建协变量（现在支持成交量数据）
                    covariates = covariate_builder.build_covariates(
                        prices=prices_array,
                        volumes=volumes_array,
                    )

                    # 验证协变量
                    validation_result = covariate_builder.validate_covariates(covariates)
                    if not validation_result['is_valid']:
                        logger.warning(
                            f"Covariate validation failed: {validation_result['warnings']}, "
                            f"falling back to standard prediction"
                        )
                        forecast_result = self._timesfm_service.predict(
                            data=prices_array,
                            horizon=max_horizon,
                        )
                    else:
                        # 使用协变量预测
                        # 获取实际使用的特征名称
                        feature_names = covariate_builder.get_feature_names()
                        forecast_result = self._timesfm_service.predict_with_covariates(
                            data=prices_array,
                            covariates=covariates,
                            horizon=max_horizon,
                            feature_names=feature_names,
                        )
                        logger.debug(
                            f"Prediction with covariates: "
                            f"n_features={validation_result['n_features']}, "
                            f"features={feature_names}"
                        )

                except ImportError:
                    logger.warning("ForecastCovariateBuilder not available, using standard prediction")
                    forecast_result = self._timesfm_service.predict(
                        data=prices_array,
                        horizon=max_horizon,
                    )
                except Exception as e:
                    logger.warning(f"Covariate building failed: {e}, falling back to standard prediction")
                    forecast_result = self._timesfm_service.predict(
                        data=prices_array,
                        horizon=max_horizon,
                    )
            else:
                # 标准预测（不使用协变量）
                forecast_result = self._timesfm_service.predict(
                    data=prices_array,
                    horizon=max_horizon,
                )

            # 转换为字典格式
            # timesfm_service.predict() 返回字典，需要转换为统一的字典格式
            predictions = forecast_result.get("predictions", [])
            trend = forecast_result.get("trend", {})
            metadata = forecast_result.get("metadata", {})

            # 计算统计信息
            import numpy as np
            pred_array = np.array(predictions)
            min_pred = float(np.min(pred_array)) if len(pred_array) > 0 else 0.0
            max_pred = float(np.max(pred_array)) if len(pred_array) > 0 else 0.0
            median_pred = float(np.median(pred_array)) if len(pred_array) > 0 else 0.0

            # 生成分位数预测（简化版本）
            horizon = len(predictions)
            quantile_forecast = np.zeros((horizon, 10))
            for i in range(10):
                # 使用 ±5% 区间模拟分位数
                factor = 0.95 + (i * 0.01)  # 0.95, 0.96, ..., 1.04, 1.05
                quantile_forecast[:, i] = pred_array * factor

            result = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "current_price": float(prices_array[-1]),
                "prediction_date": datetime.now().isoformat(),
                "point_forecast": predictions,
                "quantile_forecast": quantile_forecast.tolist(),
                "min_predicted": min_pred,
                "max_predicted": max_pred,
                "median_predicted": median_pred,
                "trend_direction": trend.get("direction", "sideways"),
                "context_length": metadata.get("context_len", len(prices_array)),
                "horizon": metadata.get("horizon_len", horizon),
                "model_version": f"TimesFM-{self._timesfm_service.model_id}",
                "generated_at": datetime.now().isoformat(),
            }

            # 生成预测图表
            chart_base64 = self._generate_forecast_chart(
                prices=prices_array,
                point_forecast=np.array(result["point_forecast"]),
                quantile_forecast=np.array(result["quantile_forecast"]),
            )
            if chart_base64:
                result["chart_base64"] = chart_base64

            return result

        except ImportError as e:
            logger.warning(f"TimesFM not available: {e}")
            return None
        except Exception as e:
            logger.warning(f"TimesFM prediction failed for {stock_code}: {e}")
            return None

    def _generate_forecast_chart(
        self,
        prices: "np.ndarray",
        point_forecast: "np.ndarray",
        quantile_forecast: "np.ndarray",
    ) -> Optional[str]:
        """
        生成预测图表的 base64 编码

        Args:
            prices: 历史价格数组
            point_forecast: 预测值数组
            quantile_forecast: 分位数预测数组

        Returns:
            base64 编码的 PNG 字符串，失败返回 None
        """
        try:
            from src.services.forecast_chart_service import generate_forecast_chart

            # 生成合成日期（历史数据无独立日期字段，使用回溯交易日）
            from datetime import datetime, timedelta
            history_len = len(prices)
            dates = []
            current = datetime.now()
            for _ in range(history_len):
                current = current - timedelta(days=1)
                while current.weekday() >= 5:
                    current = current - timedelta(days=1)
                dates.append(current.strftime("%Y-%m-%d"))
            dates.reverse()

            chart_data = generate_forecast_chart(
                prices=prices,
                dates=dates,
                point_forecast=point_forecast,
                quantile_forecast=quantile_forecast,
            )
            return chart_data.chart_base64
        except Exception as e:
            logger.warning(f"Failed to generate forecast chart: {e}")
            return None

    def _run_ensemble_forecast(
        self,
        stock_code: str,
        stock_name: str,
        historical_prices: list,
        max_context: int,
        max_horizon: int,
        device: str,
    ) -> Optional[Dict[str, Any]]:
        """
        运行集成预测（多模型融合）

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            historical_prices: 历史收盘价列表
            max_context: 最大上下文长度
            max_horizon: 最大预测天数
            device: 推理设备

        Returns:
            预测结果字典，失败时返回 None
        """
        try:
            from src.config import get_config
            from src.services.forecast_ensemble_service import (
                ForecastEnsembleService,
                ForecastModelRegistry,
                TimesFMModel,
                NaiveSeasonalModel,
                MovingAverageModel,
            )
            from src.services.forecast_accuracy_service import ForecastAccuracyService

            config = get_config()

            # 准备数据
            prices_array = np.array(historical_prices, dtype=np.float64)

            # 获取集成配置
            ensemble_models_str = getattr(config, 'timesfm_ensemble_models', 'timesfm,naive_seasonal,moving_average')
            ensemble_models = [m.strip() for m in ensemble_models_str.split(',') if m.strip()]

            ensemble_strategy_str = getattr(config, 'timesfm_ensemble_strategy', 'weighted_average')
            # 映射策略名称
            strategy_map = {
                'simple': 'simple',
                'simple_average': 'simple',
                'weighted': 'weighted',
                'weighted_average': 'weighted',
                'median': 'median',
            }
            ensemble_strategy = strategy_map.get(ensemble_strategy_str.lower(), 'weighted')

            # 构建模型列表
            models = []
            for model_name in ensemble_models:
                try:
                    if model_name == 'timesfm':
                        # 懒加载 TimesFM 服务
                        if self._timesfm_service is None:
                            from src.services.timesfm_service import TimesFMService
                            self._timesfm_service = TimesFMService(
                                context_len=max_context if max_context > 0 else 256,
                                horizon_len=max_horizon,
                                backend=device if device != 'auto' else 'cpu',
                            )
                        models.append(TimesFMModel(self._timesfm_service))
                    elif model_name == 'naive_seasonal':
                        models.append(NaiveSeasonalModel(seasonality_period=5))
                    elif model_name == 'moving_average':
                        models.append(MovingAverageModel(window=10))
                    else:
                        logger.warning(f"Unknown model '{model_name}', skipping")
                except Exception as e:
                    logger.warning(f"Failed to initialize model '{model_name}': {e}, skipping")

            if not models:
                logger.error("No models available for ensemble")
                return None

            # 创建集成服务（可选传入准确率服务用于加权）
            accuracy_service = None
            if ensemble_strategy == 'weighted':
                try:
                    accuracy_service = ForecastAccuracyService()
                except Exception as e:
                    logger.warning(f"Failed to initialize accuracy service: {e}, using equal weights")

            ensemble_service = ForecastEnsembleService(
                models=models,
                strategy=ensemble_strategy,
                accuracy_service=accuracy_service,
            )

            # 执行集成预测
            ensemble_result = ensemble_service.predict_ensemble(
                data=prices_array,
                horizon=max_horizon,
                stock_code=stock_code,
            )

            # 转换为与 TimesFM 预测兼容的格式
            from datetime import datetime

            predictions = np.array(ensemble_result["predictions"])
            trend = ensemble_result["trend"]

            # 构建分位数预测（使用预测值作为中心，添加简单置信区间）
            quantile_forecast = np.stack([
                predictions * 0.95,  # 5th percentile (简化)
                predictions,
                predictions * 1.05,  # 95th percentile (简化)
            ]).T

            result = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "current_price": float(prices_array[-1]),
                "prediction_date": datetime.now().isoformat(),
                "point_forecast": predictions.tolist(),
                "quantile_forecast": quantile_forecast.tolist(),
                "min_predicted": float(np.min(predictions)),
                "max_predicted": float(np.max(predictions)),
                "median_predicted": float(np.median(predictions)),
                "trend_direction": trend["direction"],
                "context_length": len(prices_array),
                "horizon": max_horizon,
                "model_version": f"ensemble_{ensemble_strategy}",
                "generated_at": datetime.now().isoformat(),
                "ensemble_metadata": ensemble_result["metadata"],
            }

            # 生成预测图表
            chart_base64 = self._generate_forecast_chart(
                prices=prices_array,
                point_forecast=predictions,
                quantile_forecast=quantile_forecast,
            )
            if chart_base64:
                result["chart_base64"] = chart_base64

            logger.info(
                f"Ensemble forecast completed for {stock_code}: "
                f"strategy={ensemble_strategy}, n_models={ensemble_result['metadata']['n_models']}"
            )

            return result

        except ImportError as e:
            logger.warning(f"Ensemble service not available: {e}")
            return None
        except Exception as e:
            logger.warning(f"Ensemble prediction failed for {stock_code}: {e}")
            return None

    def _build_analysis_response(
        self, 
        result: Any, 
        query_id: str,
        report_type: str = "detailed",
    ) -> Dict[str, Any]:
        """
        构建分析响应
        
        Args:
            result: AnalysisResult 对象
            query_id: 查询 ID
            report_type: 归一化后的报告类型
            
        Returns:
            格式化的响应字典
        """
        # 获取狙击点位
        sniper_points = {}
        if hasattr(result, 'get_sniper_points'):
            sniper_points = result.get_sniper_points() or {}

        # 运行 TimesFM 预测
        forecast_result = None
        if hasattr(result, 'historical_prices') and result.historical_prices:
            # 获取历史价格数据
            historical_prices = result.historical_prices
            historical_volumes = getattr(result, 'historical_volumes', None)

            forecast_result = self._run_timesfm_forecast(
                stock_code=result.code,
                stock_name=getattr(result, "name", None),
                historical_prices=historical_prices,
                historical_volumes=historical_volumes,
            )

            # Record forecast for accuracy tracking (non-blocking)
            if forecast_result is not None:
                try:
                    from src.services.forecast_accuracy_service import ForecastAccuracyService
                    accuracy_svc = ForecastAccuracyService()
                    accuracy_svc.record_forecast(
                        query_id=query_id,
                        stock_code=result.code,
                        stock_name=getattr(result, "name", None),
                        current_price=forecast_result.get("current_price", 0),
                        point_forecast=forecast_result.get("point_forecast", []),
                        quantile_forecast=forecast_result.get("quantile_forecast"),
                        horizon=forecast_result.get("horizon", 60),
                        context_length=forecast_result.get("context_length", 0),
                        model_version=forecast_result.get("model_version"),
                        trend_direction=forecast_result.get("trend_direction"),
                    )
                except Exception as e:
                    logger.debug(f"Failed to record forecast: {e}")

        # 计算情绪标签
        report_language = normalize_report_language(getattr(result, "report_language", "zh"))
        sentiment_label = get_sentiment_label(result.sentiment_score, report_language)
        stock_name = get_localized_stock_name(getattr(result, "name", None), result.code, report_language)
        
        # 构建报告结构
        report = {
            "meta": {
                "query_id": query_id,
                "stock_code": result.code,
                "stock_name": stock_name,
                "report_type": report_type,
                "report_language": report_language,
                "current_price": result.current_price,
                "change_pct": result.change_pct,
                "model_used": getattr(result, "model_used", None),
            },
            "summary": {
                "analysis_summary": result.analysis_summary,
                "operation_advice": localize_operation_advice(result.operation_advice, report_language),
                "trend_prediction": localize_trend_prediction(result.trend_prediction, report_language),
                "sentiment_score": result.sentiment_score,
                "sentiment_label": sentiment_label,
            },
            "strategy": {
                "ideal_buy": sniper_points.get("ideal_buy"),
                "secondary_buy": sniper_points.get("secondary_buy"),
                "stop_loss": sniper_points.get("stop_loss"),
                "take_profit": sniper_points.get("take_profit"),
            },
            "details": {
                "news_summary": result.news_summary,
                "technical_analysis": result.technical_analysis,
                "fundamental_analysis": result.fundamental_analysis,
                "risk_warning": result.risk_warning,
            },
            "forecast": forecast_result,
        }
        
        return {
            "stock_code": result.code,
            "stock_name": stock_name,
            "report": report,
        }
