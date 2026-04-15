# -*- coding: utf-8 -*-
"""测试 ForecastResult Schema"""

import pytest
import numpy as np
from datetime import datetime
from src.schemas.forecast_schema import ForecastResult


def test_forecast_result_creation():
    """测试 ForecastResult 创建"""
    horizon = 60
    point_forecast = np.random.rand(horizon) * 100 + 100
    quantile_forecast = np.random.rand(horizon, 10) * 50 + 100

    result = ForecastResult(
        stock_code="600519",
        stock_name="贵州茅台",
        current_price=150.0,
        prediction_date=datetime.now(),
        point_forecast=point_forecast,
        quantile_forecast=quantile_forecast,
        min_predicted=float(np.min(point_forecast)),
        max_predicted=float(np.max(point_forecast)),
        median_predicted=float(np.median(point_forecast)),
        trend_direction="up",
        context_length=512,
        horizon=horizon,
        model_version="2.5",
        generated_at=datetime.now(),
    )

    assert result.stock_code == "600519"
    assert result.point_forecast.shape == (horizon,)
    assert result.quantile_forecast.shape == (horizon, 10)


def test_confidence_interval():
    """测试置信区间获取"""
    horizon = 10
    point_forecast = np.ones(horizon) * 100
    quantile_forecast = np.tile([90, 92, 94, 96, 98, 100, 102, 104, 106, 108], (horizon, 1))

    result = ForecastResult(
        stock_code="600519",
        stock_name="贵州茅台",
        current_price=100.0,
        prediction_date=datetime.now(),
        point_forecast=point_forecast,
        quantile_forecast=quantile_forecast,
        min_predicted=90.0,
        max_predicted=108.0,
        median_predicted=100.0,
        trend_direction="sideways",
        context_length=100,
        horizon=horizon,
        model_version="2.5",
        generated_at=datetime.now(),
    )

    lower, upper = result.get_confidence_interval(0.8)
    assert np.allclose(lower, 90.0)
    assert np.allclose(upper, 108.0)


def test_to_dict():
    """测试字典转换"""
    horizon = 5
    point_forecast = np.array([100, 101, 102, 103, 104])
    quantile_forecast = np.array([[95, 97, 99, 100, 101, 102, 103, 105, 107, 109]] * horizon).reshape(horizon, 10)

    result = ForecastResult(
        stock_code="600519",
        stock_name="贵州茅台",
        current_price=100.0,
        prediction_date=datetime(2026, 4, 15, 12, 0, 0),
        point_forecast=point_forecast,
        quantile_forecast=quantile_forecast,
        min_predicted=100.0,
        max_predicted=104.0,
        median_predicted=102.0,
        trend_direction="up",
        context_length=100,
        horizon=horizon,
        model_version="2.5",
        generated_at=datetime(2026, 4, 15, 12, 0, 0),
    )

    d = result.to_dict()
    assert d["stock_code"] == "600519"
    assert isinstance(d["point_forecast"], list)
    assert len(d["point_forecast"]) == horizon
    assert d["trend_direction"] == "up"


def test_invalid_trend_direction():
    """测试无效趋势方向"""
    with pytest.raises(AssertionError):
        ForecastResult(
            stock_code="600519",
            stock_name="贵州茅台",
            current_price=100.0,
            prediction_date=datetime.now(),
            point_forecast=np.ones(5),
            quantile_forecast=np.ones((5, 10)),
            min_predicted=100.0,
            max_predicted=104.0,
            median_predicted=102.0,
            trend_direction="invalid",  # 无效值
            context_length=100,
            horizon=5,
            model_version="2.5",
            generated_at=datetime.now(),
        )
