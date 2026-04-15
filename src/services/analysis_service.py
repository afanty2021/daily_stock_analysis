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
    ) -> Optional[Dict[str, Any]]:
        """
        运行 TimesFM 预测

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            historical_prices: 历史收盘价列表

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

            forecast_result = self._timesfm_service.predict(
                prices=prices_array,
                horizon=max_horizon,
                context_length=max_context if max_context > 0 else None,
            )

            # 转换为字典格式
            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "current_price": float(forecast_result.current_price),
                "prediction_date": forecast_result.prediction_date.isoformat(),
                "point_forecast": forecast_result.point_forecast.tolist(),
                "quantile_forecast": forecast_result.quantile_forecast.tolist(),
                "min_predicted": float(forecast_result.min_predicted),
                "max_predicted": float(forecast_result.max_predicted),
                "median_predicted": float(forecast_result.median_predicted),
                "trend_direction": forecast_result.trend_direction,
                "context_length": forecast_result.context_length,
                "horizon": forecast_result.horizon,
                "model_version": forecast_result.model_version,
                "generated_at": forecast_result.generated_at.isoformat(),
            }

        except ImportError as e:
            logger.warning(f"TimesFM not available: {e}")
            return None
        except Exception as e:
            logger.warning(f"TimesFM prediction failed for {stock_code}: {e}")
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
            forecast_result = self._run_timesfm_forecast(
                stock_code=result.code,
                stock_name=getattr(result, "name", None),
                historical_prices=result.historical_prices,
            )

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
