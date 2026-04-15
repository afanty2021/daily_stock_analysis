# -*- coding: utf-8 -*-
"""
===================================
预测准确率追踪服务
===================================

职责：
1. 记录 TimesFM 预测结果到数据库
2. 评估历史预测与实际价格的对比
3. 计算准确率指标 (MAE, MAPE, RMSE, 方向准确率)
4. 生成准确率报告
5. 实时预测缓存与更新
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from threading import Lock

import numpy as np
import pandas as pd

from src.repositories.forecast_repo import ForecastRepo
from src.storage import ForecastRecord, ForecastEvaluation
from src.config import get_config

logger = logging.getLogger(__name__)


class ForecastAccuracyService:
    """预测准确率追踪服务"""

    def __init__(self, db_manager=None):
        """
        初始化服务

        Args:
            db_manager: 数据库管理器（可选，默认使用单例）
        """
        self.repo = ForecastRepo(db_manager=db_manager)

        # 实时预测缓存
        self._forecast_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = Lock()

        # 从配置读取缓存参数
        config = get_config()
        self.realtime_enabled = getattr(config, 'timesfm_realtime_update_enabled', False)
        self.cache_ttl_minutes = getattr(config, 'timesfm_cache_ttl_minutes', 60)
        self.price_change_threshold = getattr(config, 'timesfm_update_on_price_change_pct', 2.0)

        logger.debug(
            f"Real-time forecast updates: {'enabled' if self.realtime_enabled else 'disabled'}, "
            f"cache_ttl={self.cache_ttl_minutes}min, "
            f"price_change_threshold={self.price_change_threshold}%"
        )

    def record_forecast(
        self,
        query_id: str,
        stock_code: str,
        stock_name: Optional[str],
        current_price: float,
        point_forecast,
        quantile_forecast=None,
        horizon: int = 60,
        context_length: int = 0,
        model_version: Optional[str] = None,
        trend_direction: Optional[str] = None,
    ) -> Optional[ForecastRecord]:
        """
        记录预测结果到数据库

        Args:
            query_id: 关联分析记录 ID
            stock_code: 股票代码
            stock_name: 股票名称
            current_price: 当前价格
            point_forecast: 预测值数组 (numpy array 或 list)
            quantile_forecast: 分位数预测数组 (numpy array 或 list，可选)
            horizon: 预测天数
            context_length: 上下文长度
            model_version: 模型版本
            trend_direction: 趋势方向

        Returns:
            保存的 ForecastRecord，失败返回 None
        """
        try:
            # Serialize numpy arrays to JSON strings
            if isinstance(point_forecast, np.ndarray):
                point_forecast_str = json.dumps(point_forecast.tolist())
            elif isinstance(point_forecast, list):
                point_forecast_str = json.dumps(point_forecast)
            else:
                point_forecast_str = json.dumps(list(point_forecast))

            if quantile_forecast is not None:
                if isinstance(quantile_forecast, np.ndarray):
                    quantile_forecast_str = json.dumps(quantile_forecast.tolist())
                elif isinstance(quantile_forecast, list):
                    quantile_forecast_str = json.dumps(quantile_forecast)
                else:
                    quantile_forecast_str = json.dumps(list(quantile_forecast))
            else:
                quantile_forecast_str = None

            return self.repo.save_forecast(
                query_id=query_id,
                stock_code=stock_code,
                stock_name=stock_name,
                current_price=current_price,
                point_forecast=point_forecast_str,
                quantile_forecast=quantile_forecast_str,
                horizon=horizon,
                context_length=context_length,
                model_version=model_version,
                trend_direction=trend_direction,
            )
        except Exception as e:
            logger.error(f"记录预测结果失败: {e}")
            return None

    def evaluate_forecast(self, record: ForecastRecord) -> Optional[ForecastEvaluation]:
        """
        评估单条预测（获取实际价格并对比）

        Args:
            record: 预测记录

        Returns:
            评估结果，失败返回 None
        """
        try:
            # Get actual prices from data provider
            from data_provider.base import DataFetcherManager
            fetcher = DataFetcherManager()
            df, source = fetcher.get_daily_data(
                stock_code=record.stock_code,
                days=record.horizon + 10,
            )

            if df is None or df.empty:
                logger.warning(f"无法获取 {record.stock_code} 的实际价格数据")
                return None

            # Get close prices after prediction date
            prediction_date = record.prediction_date
            if hasattr(prediction_date, 'date'):
                pred_date = prediction_date.date() if hasattr(prediction_date, 'date') else prediction_date
            else:
                pred_date = prediction_date

            # Filter to dates after prediction
            if 'date' in df.columns:
                # Convert pred_date to Timestamp for proper comparison with datetime64
                pred_timestamp = pd.Timestamp(pred_date) if not isinstance(pred_date, pd.Timestamp) else pred_date
                mask = df['date'] > pred_timestamp
            elif df.index.dtype == 'datetime64[ns]' or hasattr(df.index, 'date'):
                mask = df.index.date > pred_date if hasattr(df.index, 'date') else df.index > pd.Timestamp(pred_date)
            else:
                # Fallback: use last N rows
                mask = slice(-record.horizon, None)

            actual_df = df.loc[mask]
            if actual_df.empty:
                logger.warning(f"{record.stock_code} 在预测日期后无数据")
                return None

            # Get actual close prices
            if 'close' in actual_df.columns:
                actual_close = actual_df['close'].values[:record.horizon]
            else:
                logger.warning(f"{record.stock_code} 数据缺少 close 列")
                return None

            if len(actual_close) == 0:
                logger.warning(f"{record.stock_code} 实际价格数据为空")
                return None

            # Get predicted prices
            point_forecast = np.array(json.loads(record.point_forecast))

            # Align lengths: use min of actual data points and prediction horizon
            compare_len = min(len(actual_close), len(point_forecast))
            if compare_len == 0:
                return None

            actuals = actual_close[:compare_len]
            predictions = point_forecast[:compare_len]

            # Calculate metrics
            metrics = self._calculate_metrics(predictions, actuals)

            # Determine direction correctness
            direction_correct = None
            if record.trend_direction:
                actual_trend = "up" if actuals[-1] > actuals[0] else "down" if actuals[-1] < actuals[0] else "flat"
                predicted_trend = record.trend_direction
                if predicted_trend in ("up", "down"):
                    direction_correct = actual_trend == predicted_trend
                elif predicted_trend == "sideways" or predicted_trend == "flat":
                    # For sideways/flat, check if price change is small (< 2%)
                    change_pct = abs(actuals[-1] - actuals[0]) / actuals[0] * 100
                    direction_correct = change_pct < 2.0

            # Save evaluation
            actual_prices_str = json.dumps(actuals.tolist())
            evaluation = self.repo.save_evaluation(
                forecast_record_id=record.id,
                actual_prices=actual_prices_str,
                mae=metrics["mae"],
                mape=metrics["mape"],
                rmse=metrics["rmse"],
                direction_correct=direction_correct,
            )

            logger.info(
                f"评估完成: {record.stock_code} MAPE={metrics['mape']:.4f} "
                f"MAE={metrics['mae']:.4f} RMSE={metrics['rmse']:.4f}"
            )
            return evaluation

        except Exception as e:
            logger.error(f"评估预测失败 (record_id={record.id}): {e}")
            return None

    def evaluate_pending(self) -> Dict[str, Any]:
        """
        批量评估所有待处理预测

        Returns:
            包含评估统计信息的字典
        """
        evaluated_count = 0
        error_count = 0
        errors = []

        try:
            pending = self.repo.get_pending_evaluations(min_age_days=7)
            total = len(pending)
            logger.info(f"开始批量评估，共 {total} 条待评估记录")

            for record in pending:
                try:
                    result = self.evaluate_forecast(record)
                    if result:
                        evaluated_count += 1
                    else:
                        error_count += 1
                        errors.append(f"record_id={record.id}: no result")
                except Exception as e:
                    error_count += 1
                    errors.append(f"record_id={record.id}: {e}")

            summary = {
                "total_pending": total,
                "evaluated": evaluated_count,
                "errors": error_count,
                "error_details": errors[:10],  # Limit error details
            }
            logger.info(f"批量评估完成: {evaluated_count}/{total} 成功, {error_count} 失败")
            return summary

        except Exception as e:
            logger.error(f"批量评估失败: {e}")
            return {
                "total_pending": 0,
                "evaluated": 0,
                "errors": 1,
                "error_details": [str(e)],
            }

    def get_accuracy_report(self, days: int = 30) -> Dict[str, Any]:
        """
        生成准确率报告

        Args:
            days: 统计最近多少天

        Returns:
            准确率报告字典
        """
        try:
            summary = self.repo.get_accuracy_summary(days=days)
            recent = self.repo.get_recent_forecasts(limit=10)

            return {
                "summary": summary,
                "recent_forecasts": recent,
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"生成准确率报告失败: {e}")
            return {
                "summary": {},
                "recent_forecasts": [],
                "error": str(e),
                "generated_at": datetime.now().isoformat(),
            }

    def _calculate_metrics(self, predictions: np.ndarray, actuals: np.ndarray) -> Dict[str, float]:
        """
        计算准确率指标

        Args:
            predictions: 预测值数组
            actuals: 实际值数组

        Returns:
            包含 MAE, MAPE, RMSE 的字典
        """
        # Avoid division by zero in MAPE
        nonzero_mask = actuals != 0
        if np.any(nonzero_mask):
            mape = float(np.mean(np.abs((actuals[nonzero_mask] - predictions[nonzero_mask]) / actuals[nonzero_mask])))
        else:
            mape = None

        mae = float(np.mean(np.abs(actuals - predictions)))
        rmse = float(np.sqrt(np.mean((actuals - predictions) ** 2)))

        return {
            "mae": round(mae, 4) if mae is not None else None,
            "mape": round(mape, 4) if mape is not None else None,
            "rmse": round(rmse, 4) if rmse is not None else None,
        }

    # ========== 实时预测缓存与更新 ==========

    def get_cached_forecast(
        self,
        stock_code: str,
        current_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存的预测结果

        Args:
            stock_code: 股票代码
            current_price: 当前价格（用于检查价格变化触发更新）

        Returns:
            缓存的预测结果字典，如果缓存不存在或过期返回 None
        """
        if not self.realtime_enabled:
            return None

        with self._cache_lock:
            cached = self._forecast_cache.get(stock_code)
            if not cached:
                return None

            # 检查缓存是否过期
            if self._is_stale(cached):
                logger.debug(f"Forecast cache for {stock_code} is stale")
                return None

            # 检查价格变化是否超过阈值
            if current_price is not None and "current_price" in cached:
                price_change_pct = abs(current_price - cached["current_price"]) / cached["current_price"] * 100
                if price_change_pct > self.price_change_threshold:
                    logger.debug(
                        f"Price change {price_change_pct:.2f}% for {stock_code} "
                        f"exceeds threshold {self.price_change_threshold}%"
                    )
                    return None

            # 返回缓存副本
            return cached.copy()

    def cache_forecast(
        self,
        stock_code: str,
        forecast_data: Dict[str, Any],
        current_price: float,
    ) -> None:
        """
        缓存预测结果

        Args:
            stock_code: 股票代码
            forecast_data: 预测数据（包含 predictions, trend, metadata）
            current_price: 当前价格
        """
        if not self.realtime_enabled:
            return

        with self._cache_lock:
            self._forecast_cache[stock_code] = {
                "forecast_data": forecast_data,
                "current_price": current_price,
                "cached_at": datetime.now(),
            }
            logger.debug(f"Cached forecast for {stock_code} at price {current_price}")

    def invalidate_cache(self, stock_code: Optional[str] = None) -> None:
        """
        使缓存失效

        Args:
            stock_code: 股票代码，None 表示清空所有缓存
        """
        with self._cache_lock:
            if stock_code:
                if stock_code in self._forecast_cache:
                    del self._forecast_cache[stock_code]
                    logger.debug(f"Invalidated forecast cache for {stock_code}")
            else:
                self._forecast_cache.clear()
                logger.debug("Cleared all forecast cache")

    def _is_stale(self, cached: Dict[str, Any]) -> bool:
        """
        判断缓存是否过期

        Args:
            cached: 缓存数据

        Returns:
            True if 缓存过期
        """
        cached_at = cached.get("cached_at")
        if not cached_at:
            return True

        if isinstance(cached_at, str):
            cached_at = datetime.fromisoformat(cached_at)

        age_minutes = (datetime.now() - cached_at).total_seconds() / 60
        return age_minutes > self.cache_ttl_minutes

    def update_forecast_if_stale(
        self,
        stock_code: str,
        current_price: float,
        timesfm_service,
        historical_data: np.ndarray,
        covariates: Optional[np.ndarray] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        检查预测是否过期，过期则重新预测

        Args:
            stock_code: 股票代码
            current_price: 当前价格
            timesfm_service: TimesFM 服务实例
            historical_data: 历史价格数据
            covariates: 协变量数据（可选）

        Returns:
            预测结果字典（来自缓存或新生成），失败返回 None
        """
        # 尝试从缓存获取
        cached = self.get_cached_forecast(stock_code, current_price)
        if cached:
            logger.debug(f"Using cached forecast for {stock_code}")
            return cached["forecast_data"]

        # 缓存未命中，重新预测
        logger.info(f"Generating fresh forecast for {stock_code}")
        try:
            # 根据是否启用协变量选择预测方法
            config = get_config()
            use_covariates = getattr(config, 'timesfm_covariates_enabled', False)

            if use_covariates and covariates is not None:
                # 获取特征名称
                feature_names_str = getattr(config, 'timesfm_covariate_features', 'volume_change,ma_deviation')
                feature_names = feature_names_str.split(',')

                result = timesfm_service.predict_with_covariates(
                    data=historical_data,
                    covariates=covariates,
                    horizon=getattr(config, 'timesfm_max_horizon', 60),
                    feature_names=feature_names,
                )
            else:
                result = timesfm_service.predict(
                    data=historical_data,
                    horizon=getattr(config, 'timesfm_max_horizon', 60),
                )

            # 缓存结果
            self.cache_forecast(stock_code, result, current_price)
            return result

        except Exception as e:
            logger.error(f"Failed to update forecast for {stock_code}: {e}")
            return None

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            缓存统计字典
        """
        with self._cache_lock:
            total = len(self._forecast_cache)
            stale_count = sum(1 for c in self._forecast_cache.values() if self._is_stale(c))

            return {
                "total_cached": total,
                "stale_count": stale_count,
                "fresh_count": total - stale_count,
                "cache_ttl_minutes": self.cache_ttl_minutes,
                "realtime_enabled": self.realtime_enabled,
                "price_change_threshold_pct": self.price_change_threshold,
            }
