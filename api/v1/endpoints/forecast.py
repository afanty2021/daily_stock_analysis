# -*- coding: utf-8 -*-
"""Forecast accuracy tracking endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException

from api.deps import get_database_manager
from src.services.forecast_accuracy_service import ForecastAccuracyService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/accuracy",
    summary="获取总体预测准确率",
    description="获取 TimesFM 预测的总体准确率统计",
)
async def get_accuracy(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> dict:
    """获取总体预测准确率"""
    try:
        service = ForecastAccuracyService(db_manager=db_manager)
        report = service.get_accuracy_report(days=days)
        return report
    except Exception as exc:
        logger.error(f"获取预测准确率失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取预测准确率失败: {str(exc)}"},
        )


@router.get(
    "/accuracy/{stock_code}",
    summary="获取单股预测准确率",
    description="获取指定股票的 TimesFM 预测准确率统计",
)
async def get_stock_accuracy(
    stock_code: str,
    days: int = Query(90, ge=1, le=365, description="统计天数"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> dict:
    """获取单股预测准确率"""
    try:
        from src.repositories.forecast_repo import ForecastRepo
        repo = ForecastRepo(db_manager=db_manager)
        return repo.get_stock_accuracy(stock_code=stock_code, days=days)
    except Exception as exc:
        logger.error(f"获取股票预测准确率失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取股票预测准确率失败: {str(exc)}"},
        )


@router.post(
    "/evaluate",
    summary="触发批量评估",
    description="触发对所有待处理预测记录的批量评估",
)
async def trigger_evaluation(
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> dict:
    """触发批量评估待处理预测"""
    try:
        service = ForecastAccuracyService(db_manager=db_manager)
        result = service.evaluate_pending()
        return result
    except Exception as exc:
        logger.error(f"批量评估失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"批量评估失败: {str(exc)}"},
        )


@router.get(
    "/records",
    summary="获取最近预测记录",
    description="获取最近的 TimesFM 预测记录列表",
)
async def get_forecast_records(
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> dict:
    """获取最近预测记录"""
    try:
        from src.repositories.forecast_repo import ForecastRepo
        repo = ForecastRepo(db_manager=db_manager)
        records = repo.get_recent_forecasts(limit=limit)
        return {"total": len(records), "records": records}
    except Exception as exc:
        logger.error(f"获取预测记录失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取预测记录失败: {str(exc)}"},
        )


@router.get(
    "/live/{stock_code}",
    summary="获取实时预测",
    description="获取指定股票的实时 TimesFM 预测（使用缓存）",
)
async def get_live_forecast(
    stock_code: str,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> dict:
    """获取实时预测"""
    try:
        from src.services.forecast_accuracy_service import ForecastAccuracyService
        from data_provider.base import normalize_stock_code

        normalized_code = normalize_stock_code(stock_code)
        service = ForecastAccuracyService(db_manager=db_manager)

        # 获取缓存统计
        stats = service.get_cache_stats()

        # 尝试获取缓存
        cached = service.get_cached_forecast(normalized_code)

        return {
            "stock_code": normalized_code,
            "cached": cached is not None,
            "forecast": cached.get("forecast_data") if cached else None,
            "cached_at": cached.get("cached_at").isoformat() if cached and cached.get("cached_at") else None,
            "cache_stats": stats,
        }
    except Exception as exc:
        logger.error(f"获取实时预测失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取实时预测失败: {str(exc)}"},
        )


@router.post(
    "/refresh/{stock_code}",
    summary="强制刷新预测",
    description="强制重新生成指定股票的 TimesFM 预测并更新缓存",
)
async def refresh_forecast(
    stock_code: str,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> dict:
    """强制刷新预测"""
    try:
        from src.services.forecast_accuracy_service import ForecastAccuracyService
        from src.services.timesfm_service import TimesFMService
        from data_provider.base import normalize_stock_code, DataFetcherManager

        normalized_code = normalize_stock_code(stock_code)

        # 获取历史数据
        fetcher = DataFetcherManager()
        df, source = fetcher.get_daily_data(
            stock_code=normalized_code,
            days=256,  # 足够的历史数据
        )

        if df is None or df.empty or len(df) < 32:
            raise HTTPException(
                status_code=400,
                detail={"error": "insufficient_data", "message": f"无法获取足够的历史数据"},
            )

        # 获取当前价格
        current_price = float(df['close'].iloc[-1])

        # 准备历史数据
        import numpy as np
        historical_data = df['close'].values

        # 初始化服务
        service = ForecastAccuracyService(db_manager=db_manager)
        timesfm_service = TimesFMService(
            context_len=256,
            horizon_len=60,
            backend="cpu",
        )

        # 使缓存失效并重新预测
        service.invalidate_cache(normalized_code)
        result = service.update_forecast_if_stale(
            stock_code=normalized_code,
            current_price=current_price,
            timesfm_service=timesfm_service,
            historical_data=historical_data,
        )

        if result is None:
            raise HTTPException(
                status_code=500,
                detail={"error": "prediction_failed", "message": "预测生成失败"},
            )

        return {
            "stock_code": normalized_code,
            "forecast": result,
            "refreshed_at": datetime.now().isoformat(),
            "data_source": source,
            "current_price": current_price,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"刷新预测失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"刷新预测失败: {str(exc)}"},
        )


@router.get(
    "/cache/stats",
    summary="获取缓存统计",
    description="获取预测缓存的统计信息",
)
async def get_cache_stats(
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> dict:
    """获取缓存统计"""
    try:
        from src.services.forecast_accuracy_service import ForecastAccuracyService
        service = ForecastAccuracyService(db_manager=db_manager)
        return service.get_cache_stats()
    except Exception as exc:
        logger.error(f"获取缓存统计失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取缓存统计失败: {str(exc)}"},
        )


@router.post(
    "/cache/invalidate",
    summary="清空缓存",
    description="清空所有预测缓存或指定股票的缓存",
)
async def invalidate_cache(
    stock_code: Optional[str] = Query(None, description="股票代码，不提供则清空所有缓存"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> dict:
    """清空缓存"""
    try:
        from src.services.forecast_accuracy_service import ForecastAccuracyService
        service = ForecastAccuracyService(db_manager=db_manager)
        service.invalidate_cache(stock_code)
        return {
            "message": f"缓存已清空: {stock_code if stock_code else '全部'}",
            "stock_code": stock_code,
        }
    except Exception as exc:
        logger.error(f"清空缓存失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"清空缓存失败: {str(exc)}"},
        )
