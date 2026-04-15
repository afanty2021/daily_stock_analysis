# -*- coding: utf-8 -*-
"""测试 TimesFM 预测图表生成服务"""

import base64
import pytest
import numpy as np

from src.schemas.forecast_chart_schema import ForecastChartConfig, ForecastChartData
from src.services.forecast_chart_service import (
    generate_forecast_chart,
    _chart_to_base64,
    _generate_forecast_dates,
)


# ── 固定测试数据 ──────────────────────────────────────────────

def _make_mock_data(history_len: int = 90, horizon: int = 20):
    """生成 mock 数据用于图表测试"""
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(history_len) * 0.5) + 100
    dates = [f"2026-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}" for i in range(history_len)]
    point_forecast = prices[-1] + np.cumsum(np.random.randn(horizon) * 0.3)
    quantile_forecast = np.random.rand(horizon, 10) * 5 + point_forecast.reshape(-1, 1) - 2.5
    # 确保分位数递增
    quantile_forecast.sort(axis=1)
    return prices, dates, point_forecast, quantile_forecast


# ── 核心图表生成测试 ─────────────────────────────────────────

class TestGenerateForecastChart:
    """generate_forecast_chart 核心功能"""

    def test_basic_chart_generation(self):
        """基本图表生成，返回 ForecastChartData"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data()

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast)

        assert isinstance(result, ForecastChartData)
        assert isinstance(result.chart_base64, str)
        assert len(result.chart_base64) > 100  # base64 PNG 有一定长度

    def test_base64_is_valid_png(self):
        """base64 解码后为合法 PNG 字节"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data()

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast)

        raw = base64.b64decode(result.chart_base64)
        assert raw[:4] == b"\x89PNG"

    def test_chart_without_confidence(self):
        """关闭置信区间仍可正常生成"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data()
        config = ForecastChartConfig(show_confidence=False)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast, config=config)

        assert isinstance(result, ForecastChartData)
        assert len(result.chart_base64) > 50

    def test_chart_with_none_quantile(self):
        """quantile_forecast 为 None 时不报错"""
        prices, dates, point_forecast, _ = _make_mock_data()
        config = ForecastChartConfig(show_confidence=True)

        result = generate_forecast_chart(prices, dates, point_forecast, None, config=config)

        assert isinstance(result, ForecastChartData)

    def test_custom_config_dimensions(self):
        """自定义宽高 DPI 生成的图表尺寸"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data()
        config = ForecastChartConfig(width=8, height=4, dpi=100)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast, config=config)

        assert result.width == 8
        assert result.height == 4


class TestForecastChartConfig:
    """ForecastChartConfig 默认值"""

    def test_defaults(self):
        config = ForecastChartConfig()
        assert config.width == 12
        assert config.height == 6
        assert config.dpi == 150
        assert config.show_confidence is True
        assert config.confidence_level == 0.8
        assert config.show_history_days == 90
        assert config.format == "png"

    def test_custom_values(self):
        config = ForecastChartConfig(
            width=10,
            height=5,
            dpi=120,
            show_confidence=False,
            confidence_level=0.6,
            show_history_days=60,
        )
        assert config.width == 10
        assert config.dpi == 120
        assert config.show_confidence is False
        assert config.confidence_level == 0.6
        assert config.show_history_days == 60


class TestForecastChartData:
    """ForecastChartData 数据类"""

    def test_creation(self):
        data = ForecastChartData(chart_base64="abc123")
        assert data.chart_base64 == "abc123"
        assert data.chart_path is None
        assert data.width == 0
        assert data.height == 0

    def test_with_path(self):
        data = ForecastChartData(
            chart_base64="abc123",
            chart_path="/tmp/chart.png",
            width=800,
            height=400,
        )
        assert data.chart_path == "/tmp/chart.png"
        assert data.width == 800


class TestHistoryTruncation:
    """历史天数截断"""

    def test_truncation_applied(self):
        """show_history_days 小于数据长度时截断"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data(history_len=200)
        config = ForecastChartConfig(show_history_days=30)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast, config=config)

        assert isinstance(result, ForecastChartData)
        # 无法直接检查 prices 是否被截断（内部处理），但应不报错

    def test_no_truncation_when_zero(self):
        """show_history_days=0 不截断"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data(history_len=50)
        config = ForecastChartConfig(show_history_days=0)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast, config=config)
        assert isinstance(result, ForecastChartData)

    def test_show_all_history(self):
        """show_history_days 大于数据长度时不截断"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data(history_len=30)
        config = ForecastChartConfig(show_history_days=90)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast, config=config)
        assert isinstance(result, ForecastChartData)


class TestGenerateForecastDates:
    """预测日期生成"""

    def test_basic_date_generation(self):
        dates = _generate_forecast_dates(["2026-04-15"], horizon=5)
        assert len(dates) == 5
        # 第一个预测日应为 2026-04-16（周三）
        assert dates[0] == "2026-04-16"

    def test_skip_weekends(self):
        # 2026-04-17 是周五，预测 3 天应跳过周末
        dates = _generate_forecast_dates(["2026-04-17"], horizon=3)
        assert len(dates) == 3
        # 周五 -> 周一 -> 周二 -> 周三
        assert dates[0] == "2026-04-20"  # 周一
        assert dates[1] == "2026-04-21"  # 周二
        assert dates[2] == "2026-04-22"  # 周三

    def test_empty_history_dates(self):
        dates = _generate_forecast_dates([], horizon=3)
        assert len(dates) == 3

    def test_invalid_date_format(self):
        """无效日期格式应使用当前日期"""
        dates = _generate_forecast_dates(["not-a-date"], horizon=3)
        assert len(dates) == 3


class TestConfidenceBand:
    """置信区间渲染"""

    def test_80_percent_confidence(self):
        """80% 置信区间使用 10%/90% 分位数"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data()
        config = ForecastChartConfig(confidence_level=0.8)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast, config=config)
        assert isinstance(result, ForecastChartData)

    def test_60_percent_confidence(self):
        """60% 置信区间使用 20%/80% 分位数"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data()
        config = ForecastChartConfig(confidence_level=0.6)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast, config=config)
        assert isinstance(result, ForecastChartData)


class TestEdgeCases:
    """边界情况"""

    def test_short_history(self):
        """历史数据非常短（10 天）"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data(history_len=10, horizon=5)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast)
        assert isinstance(result, ForecastChartData)

    def test_large_horizon(self):
        """预测步数较多（60 步）"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data(history_len=120, horizon=60)

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast)
        assert isinstance(result, ForecastChartData)

    def test_default_config_when_none(self):
        """config=None 使用默认配置"""
        prices, dates, point_forecast, quantile_forecast = _make_mock_data()

        result = generate_forecast_chart(prices, dates, point_forecast, quantile_forecast, config=None)
        assert isinstance(result, ForecastChartData)
