# -*- coding: utf-8 -*-
"""
===================================
预测准确率数据访问层
===================================

职责：
1. 封装预测记录和评估结果的数据库操作
2. 提供 CRUD 和统计查询接口
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import func, and_, desc

from src.storage import DatabaseManager, ForecastRecord, ForecastEvaluation

logger = logging.getLogger(__name__)


class ForecastRepo:
    """
    预测准确率数据访问层

    封装 ForecastRecord 和 ForecastEvaluation 表的数据库操作
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        初始化数据访问层

        Args:
            db_manager: 数据库管理器（可选，默认使用单例）
        """
        self.db = db_manager or DatabaseManager.get_instance()

    def save_forecast(
        self,
        query_id: str,
        stock_code: str,
        stock_name: Optional[str],
        current_price: float,
        point_forecast: str,
        quantile_forecast: Optional[str],
        horizon: int,
        context_length: int,
        model_version: Optional[str],
        trend_direction: Optional[str],
    ) -> Optional[ForecastRecord]:
        """
        保存预测记录

        Args:
            query_id: 关联分析记录 ID
            stock_code: 股票代码
            stock_name: 股票名称
            current_price: 当前价格
            point_forecast: JSON 序列化的预测值数组
            quantile_forecast: JSON 序列化的分位数预测数组
            horizon: 预测天数
            context_length: 上下文长度
            model_version: 模型版本
            trend_direction: 趋势方向

        Returns:
            保存的 ForecastRecord，失败返回 None
        """
        try:
            record = ForecastRecord(
                query_id=query_id,
                stock_code=stock_code,
                stock_name=stock_name,
                current_price=current_price,
                point_forecast=point_forecast,
                quantile_forecast=quantile_forecast,
                horizon=horizon,
                context_length=context_length,
                model_version=model_version,
                trend_direction=trend_direction,
            )
            with self.db.session_scope() as session:
                session.add(record)
                session.flush()
                # Detach to use outside session
                session.expunge(record)
            return record
        except Exception as e:
            logger.error(f"保存预测记录失败: {e}")
            return None

    def get_pending_evaluations(self, min_age_days: int = 7) -> List[ForecastRecord]:
        """
        获取待评估的预测记录

        查询 evaluated=False 且预测日期距今超过 horizon 天的记录

        Args:
            min_age_days: 最小预测经过天数

        Returns:
            待评估的 ForecastRecord 列表
        """
        try:
            cutoff = datetime.now() - timedelta(days=min_age_days)
            with self.db.get_session() as session:
                # Find records where evaluated=False and prediction_date + horizon days <= now
                results = (
                    session.query(ForecastRecord)
                    .filter(
                        and_(
                            ForecastRecord.evaluated == False,  # noqa: E712
                            ForecastRecord.prediction_date <= cutoff,
                        )
                    )
                    .order_by(ForecastRecord.prediction_date)
                    .all()
                )
                # Detach all records
                for r in results:
                    session.expunge(r)
                return results
        except Exception as e:
            logger.error(f"获取待评估记录失败: {e}")
            return []

    def save_evaluation(
        self,
        forecast_record_id: int,
        actual_prices: str,
        mae: Optional[float],
        mape: Optional[float],
        rmse: Optional[float],
        direction_correct: Optional[bool],
    ) -> Optional[ForecastEvaluation]:
        """
        保存评估结果

        Args:
            forecast_record_id: 预测记录 ID
            actual_prices: JSON 序列化的实际价格数组
            mae: 平均绝对误差
            mape: 平均绝对百分比误差
            rmse: 均方根误差
            direction_correct: 方向是否正确

        Returns:
            保存的 ForecastEvaluation，失败返回 None
        """
        try:
            evaluation = ForecastEvaluation(
                forecast_record_id=forecast_record_id,
                actual_prices=actual_prices,
                mae=mae,
                mape=mape,
                rmse=rmse,
                direction_correct=direction_correct,
            )
            with self.db.session_scope() as session:
                session.add(evaluation)
                # Mark forecast record as evaluated
                record = (
                    session.query(ForecastRecord)
                    .filter(ForecastRecord.id == forecast_record_id)
                    .first()
                )
                if record:
                    record.evaluated = True
                session.flush()
                session.expunge(evaluation)
            return evaluation
        except Exception as e:
            logger.error(f"保存评估结果失败: {e}")
            return None

    def get_accuracy_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        获取总体准确率摘要

        Args:
            days: 统计最近多少天

        Returns:
            包含总体 MAPE、方向准确率、记录数的字典
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            with self.db.get_session() as session:
                # Overall MAPE
                mape_result = (
                    session.query(func.avg(ForecastEvaluation.mape))
                    .filter(ForecastEvaluation.evaluated_at >= cutoff)
                    .scalar()
                )
                # Overall MAE
                mae_result = (
                    session.query(func.avg(ForecastEvaluation.mae))
                    .filter(ForecastEvaluation.evaluated_at >= cutoff)
                    .scalar()
                )
                # Overall RMSE
                rmse_result = (
                    session.query(func.avg(ForecastEvaluation.rmse))
                    .filter(ForecastEvaluation.evaluated_at >= cutoff)
                    .scalar()
                )
                # Direction accuracy
                total_dir = (
                    session.query(func.count(ForecastEvaluation.id))
                    .filter(
                        and_(
                            ForecastEvaluation.evaluated_at >= cutoff,
                            ForecastEvaluation.direction_correct.isnot(None),
                        )
                    )
                    .scalar()
                )
                correct_dir = (
                    session.query(func.count(ForecastEvaluation.id))
                    .filter(
                        and_(
                            ForecastEvaluation.evaluated_at >= cutoff,
                            ForecastEvaluation.direction_correct == True,  # noqa: E712
                        )
                    )
                    .scalar()
                )
                # Total evaluations
                total_eval = (
                    session.query(func.count(ForecastEvaluation.id))
                    .filter(ForecastEvaluation.evaluated_at >= cutoff)
                    .scalar()
                )

            return {
                "days": days,
                "total_evaluations": total_eval or 0,
                "avg_mape": round(mape_result, 4) if mape_result else None,
                "avg_mae": round(mae_result, 4) if mae_result else None,
                "avg_rmse": round(rmse_result, 4) if rmse_result else None,
                "direction_accuracy": round(correct_dir / total_dir, 4) if total_dir and total_dir > 0 else None,
                "direction_total": total_dir or 0,
                "direction_correct": correct_dir or 0,
            }
        except Exception as e:
            logger.error(f"获取准确率摘要失败: {e}")
            return {
                "days": days,
                "total_evaluations": 0,
                "avg_mape": None,
                "avg_mae": None,
                "avg_rmse": None,
                "direction_accuracy": None,
                "direction_total": 0,
                "direction_correct": 0,
            }

    def get_stock_accuracy(self, stock_code: str, days: int = 90) -> Dict[str, Any]:
        """
        获取单只股票的预测准确率

        Args:
            stock_code: 股票代码
            days: 统计最近多少天

        Returns:
            包含单股 MAPE、方向准确率等的字典
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            with self.db.get_session() as session:
                # Join forecast_records with forecast_evaluations
                mape_result = (
                    session.query(func.avg(ForecastEvaluation.mape))
                    .join(ForecastRecord, ForecastEvaluation.forecast_record_id == ForecastRecord.id)
                    .filter(
                        and_(
                            ForecastRecord.stock_code == stock_code,
                            ForecastEvaluation.evaluated_at >= cutoff,
                        )
                    )
                    .scalar()
                )
                mae_result = (
                    session.query(func.avg(ForecastEvaluation.mae))
                    .join(ForecastRecord, ForecastEvaluation.forecast_record_id == ForecastRecord.id)
                    .filter(
                        and_(
                            ForecastRecord.stock_code == stock_code,
                            ForecastEvaluation.evaluated_at >= cutoff,
                        )
                    )
                    .scalar()
                )
                rmse_result = (
                    session.query(func.avg(ForecastEvaluation.rmse))
                    .join(ForecastRecord, ForecastEvaluation.forecast_record_id == ForecastRecord.id)
                    .filter(
                        and_(
                            ForecastRecord.stock_code == stock_code,
                            ForecastEvaluation.evaluated_at >= cutoff,
                        )
                    )
                    .scalar()
                )
                total_dir = (
                    session.query(func.count(ForecastEvaluation.id))
                    .join(ForecastRecord, ForecastEvaluation.forecast_record_id == ForecastRecord.id)
                    .filter(
                        and_(
                            ForecastRecord.stock_code == stock_code,
                            ForecastEvaluation.evaluated_at >= cutoff,
                            ForecastEvaluation.direction_correct.isnot(None),
                        )
                    )
                    .scalar()
                )
                correct_dir = (
                    session.query(func.count(ForecastEvaluation.id))
                    .join(ForecastRecord, ForecastEvaluation.forecast_record_id == ForecastRecord.id)
                    .filter(
                        and_(
                            ForecastRecord.stock_code == stock_code,
                            ForecastEvaluation.evaluated_at >= cutoff,
                            ForecastEvaluation.direction_correct == True,  # noqa: E712
                        )
                    )
                    .scalar()
                )
                total_eval = (
                    session.query(func.count(ForecastEvaluation.id))
                    .join(ForecastRecord, ForecastEvaluation.forecast_record_id == ForecastRecord.id)
                    .filter(
                        and_(
                            ForecastRecord.stock_code == stock_code,
                            ForecastEvaluation.evaluated_at >= cutoff,
                        )
                    )
                    .scalar()
                )

            return {
                "stock_code": stock_code,
                "days": days,
                "total_evaluations": total_eval or 0,
                "avg_mape": round(mape_result, 4) if mape_result else None,
                "avg_mae": round(mae_result, 4) if mae_result else None,
                "avg_rmse": round(rmse_result, 4) if rmse_result else None,
                "direction_accuracy": round(correct_dir / total_dir, 4) if total_dir and total_dir > 0 else None,
                "direction_total": total_dir or 0,
                "direction_correct": correct_dir or 0,
            }
        except Exception as e:
            logger.error(f"获取股票准确率失败: {e}")
            return {
                "stock_code": stock_code,
                "days": days,
                "total_evaluations": 0,
                "avg_mape": None,
                "avg_mae": None,
                "avg_rmse": None,
                "direction_accuracy": None,
                "direction_total": 0,
                "direction_correct": 0,
            }

    def get_recent_forecasts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取最近的预测记录

        Args:
            limit: 返回数量限制

        Returns:
            预测记录字典列表
        """
        try:
            with self.db.get_session() as session:
                records = (
                    session.query(ForecastRecord)
                    .order_by(desc(ForecastRecord.created_at))
                    .limit(limit)
                    .all()
                )
                result = []
                for r in records:
                    result.append({
                        "id": r.id,
                        "query_id": r.query_id,
                        "stock_code": r.stock_code,
                        "stock_name": r.stock_name,
                        "prediction_date": r.prediction_date.isoformat() if r.prediction_date else None,
                        "current_price": r.current_price,
                        "point_forecast": r.point_forecast,
                        "horizon": r.horizon,
                        "context_length": r.context_length,
                        "model_version": r.model_version,
                        "trend_direction": r.trend_direction,
                        "evaluated": r.evaluated,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    })
                return result
        except Exception as e:
            logger.error(f"获取最近预测记录失败: {e}")
            return []
