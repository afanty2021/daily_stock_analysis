# -*- coding: utf-8 -*-
"""
===================================
协变量构建器测试
===================================

测试 ForecastCovariateBuilder 的各项功能：
- 协变量构建
- 数据验证
- 特征标准化
- 异常处理
"""

import pytest
import numpy as np
import pandas as pd

from src.services.forecast_covariate_builder import (
    ForecastCovariateBuilder,
    CovariateFeature,
    CovariateBuilderError,
    InsufficientDataError,
    ValidationError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_price_data():
    """生成示例价格数据"""
    np.random.seed(42)
    n_points = 300
    # 生成带有趋势和噪声的数据
    trend = np.linspace(100, 150, n_points)
    noise = np.random.randn(n_points) * 5
    prices = trend + noise
    return prices.astype(np.float64)


@pytest.fixture
def sample_volume_data():
    """生成示例成交量数据"""
    np.random.seed(42)
    n_points = 300
    # 生成带有波动性的成交量数据
    base_volume = 1000000
    volume = base_volume + np.random.randn(n_points) * 200000
    volume = np.abs(volume)  # 确保非负
    return volume.astype(np.float64)


@pytest.fixture
def builder():
    """创建协变量构建器实例"""
    return ForecastCovariateBuilder()


# =============================================================================
# 基础功能测试
# =============================================================================


class TestBasicFunctionality:
    """测试基础功能"""

    def test_init_default_params(self):
        """测试默认参数初始化"""
        builder = ForecastCovariateBuilder()
        assert len(builder.enabled_features) == 4
        assert builder.rsi_period == 14
        assert builder.ma_periods == [5, 10, 20]
        assert builder.bollinger_period == 20
        assert builder.bollinger_std == 2

    def test_init_custom_params(self):
        """测试自定义参数初始化"""
        builder = ForecastCovariateBuilder(
            enabled_features=["volume_change", "rsi"],
            rsi_period=10,
            ma_periods=[5, 20],
            bollinger_period=15,
            bollinger_std=1.5,
        )
        assert len(builder.enabled_features) == 2
        assert builder.rsi_period == 10
        assert builder.ma_periods == [5, 20]
        assert builder.bollinger_period == 15
        assert builder.bollinger_std == 1.5

    def test_build_covariates_basic(self, builder, sample_price_data):
        """测试基本的协变量构建"""
        covariates = builder.build_covariates(prices=sample_price_data)

        # 验证形状
        assert covariates.ndim == 2
        assert covariates.shape[0] == len(sample_price_data)
        assert covariates.shape[1] == len(builder.enabled_features)

    def test_build_covariates_with_volumes(
        self, builder, sample_price_data, sample_volume_data
    ):
        """测试带成交量的协变量构建"""
        covariates = builder.build_covariates(
            prices=sample_price_data,
            volumes=sample_volume_data,
        )

        # 验证形状
        assert covariates.shape[0] == len(sample_price_data)
        assert covariates.shape[1] == len(builder.enabled_features)


# =============================================================================
# 特征构建测试
# =============================================================================


class TestFeatureBuilding:
    """测试特征构建"""

    def test_volume_change_feature(self):
        """测试成交量变化率特征"""
        builder = ForecastCovariateBuilder(
            enabled_features=["volume_change"]
        )

        prices = np.linspace(100, 150, 100)
        volumes = np.random.randn(100) * 100000 + 1000000
        volumes = np.abs(volumes)

        covariates = builder.build_covariates(prices=prices, volumes=volumes)

        # 验证形状
        assert covariates.shape == (100, 1)

        # 验证数值范围（应该在 [-1, 1] 附近）
        assert np.abs(covariates).max() <= 1.0

    def test_volume_change_without_volumes(self):
        """测试无成交量数据时的行为"""
        builder = ForecastCovariateBuilder(
            enabled_features=["volume_change"]
        )

        prices = np.linspace(100, 150, 100)
        covariates = builder.build_covariates(prices=prices, volumes=None)

        # 应该返回零特征
        assert np.allclose(covariates, 0.0)

    def test_ma_deviation_feature(self):
        """测试 MA 偏离度特征"""
        builder = ForecastCovariateBuilder(
            enabled_features=["ma_deviation"]
        )

        prices = np.linspace(100, 150, 100)
        covariates = builder.build_covariates(prices=prices)

        # 验证形状
        assert covariates.shape == (100, 1)

        # 验证数值范围
        assert np.abs(covariates).max() <= 1.0

    def test_rsi_feature(self):
        """测试 RSI 特征"""
        builder = ForecastCovariateBuilder(
            enabled_features=["rsi"]
        )

        prices = np.linspace(100, 150, 100)
        covariates = builder.build_covariates(prices=prices)

        # 验证形状
        assert covariates.shape == (100, 1)

        # RSI 应该在 [0, 1] 范围内
        assert covariates.min() >= 0.0
        assert covariates.max() <= 1.0

    def test_bollinger_position_feature(self):
        """测试布林带位置特征"""
        builder = ForecastCovariateBuilder(
            enabled_features=["bollinger_position"]
        )

        prices = np.linspace(100, 150, 100)
        covariates = builder.build_covariates(prices=prices)

        # 验证形状
        assert covariates.shape == (100, 1)

        # 位置应该在 [0, 1] 范围内
        assert covariates.min() >= 0.0
        assert covariates.max() <= 1.0

    def test_multiple_features(self, builder, sample_price_data):
        """测试多个特征同时构建"""
        covariates = builder.build_covariates(prices=sample_price_data)

        # 验证所有特征都被构建
        assert covariates.shape[1] == len(builder.enabled_features)

        # 验证没有 NaN 值
        assert not np.isnan(covariates).any()

    def test_unknown_feature_skipped(self):
        """测试未知特征被跳过"""
        builder = ForecastCovariateBuilder(
            enabled_features=["unknown_feature", "ma_deviation"]
        )

        prices = np.linspace(100, 150, 100)
        covariates = builder.build_covariates(prices=prices)

        # 应该只构建 ma_deviation 特征
        assert covariates.shape == (100, 1)


# =============================================================================
# 数据验证测试
# =============================================================================


class TestDataValidation:
    """测试数据验证"""

    def test_validate_input_valid_data(self, builder, sample_price_data):
        """测试有效数据验证"""
        # 不应该抛出异常
        builder._validate_input(sample_price_data)

    def test_validate_input_insufficient_data(self, builder):
        """测试数据不足验证"""
        short_data = np.random.randn(10)

        with pytest.raises(InsufficientDataError):
            builder._validate_input(short_data)

    def test_validate_input_non_array_data(self, builder):
        """测试非数组数据验证"""
        with pytest.raises(ValidationError):
            builder._validate_input([1, 2, 3, 4, 5])

    def test_validate_input_mismatched_volumes(self, builder, sample_price_data):
        """测试成交量长度不匹配"""
        volumes = np.random.randn(50)  # 长度不匹配

        with pytest.raises(ValidationError):
            builder._validate_input(sample_price_data, volumes)

    def test_validate_input_with_inf(self, builder):
        """测试包含 Inf 的数据"""
        data = np.array([1.0, 2.0, np.inf, 4.0, 5.0] * 20)

        with pytest.raises(ValidationError):
            builder._validate_input(data)


# =============================================================================
# 协变量验证测试
# =============================================================================


class TestCovariateValidation:
    """测试协变量验证"""

    def test_validate_covariates_valid(self, builder, sample_price_data):
        """测试有效协变量验证"""
        covariates = builder.build_covariates(prices=sample_price_data)
        result = builder.validate_covariates(covariates)

        assert result["is_valid"] is True
        assert result["n_samples"] == len(sample_price_data)
        assert result["n_features"] == len(builder.enabled_features)
        assert result["nan_count"] == 0
        assert result["inf_count"] == 0
        assert len(result["warnings"]) == 0

    def test_validate_covariates_with_nan(self, builder):
        """测试包含 NaN 的协变量"""
        covariates = np.array([
            [1.0, 2.0],
            [np.nan, 3.0],
            [4.0, 5.0],
        ])
        result = builder.validate_covariates(covariates)

        assert result["is_valid"] is False
        assert result["nan_count"] == 1
        assert len(result["warnings"]) > 0

    def test_validate_covariates_with_inf(self, builder):
        """测试包含 Inf 的协变量"""
        covariates = np.array([
            [1.0, 2.0],
            [np.inf, 3.0],
            [4.0, 5.0],
        ])
        result = builder.validate_covariates(covariates)

        assert result["is_valid"] is False
        assert result["inf_count"] == 1
        assert len(result["warnings"]) > 0

    def test_validate_covariates_wrong_shape(self, builder):
        """测试错误形状的协变量"""
        covariates = np.array([1.0, 2.0, 3.0])  # 1D 数组
        result = builder.validate_covariates(covariates)

        assert result["is_valid"] is False
        assert len(result["warnings"]) > 0


# =============================================================================
# 标准化测试
# =============================================================================


class TestNormalization:
    """测试标准化功能"""

    def test_normalize_standard(self, builder, sample_price_data):
        """测试 Z-score 标准化"""
        covariates = builder.build_covariates(prices=sample_price_data)
        normalized = builder.normalize_covariates(covariates, method="standard")

        # 验证形状不变
        assert normalized.shape == covariates.shape

        # 验证没有 NaN/Inf
        assert not np.isnan(normalized).any()
        assert not np.isinf(normalized).any()

    def test_normalize_minmax(self, builder, sample_price_data):
        """测试 Min-Max 标准化"""
        covariates = builder.build_covariates(prices=sample_price_data)
        normalized = builder.normalize_covariates(covariates, method="minmax")

        # 验证形状不变
        assert normalized.shape == covariates.shape

        # 验证数值范围在 [0, 1]
        assert normalized.min() >= 0.0
        assert normalized.max() <= 1.0

    def test_normalize_robust(self, builder, sample_price_data):
        """测试鲁棒标准化"""
        covariates = builder.build_covariates(prices=sample_price_data)
        normalized = builder.normalize_covariates(covariates, method="robust")

        # 验证形状不变
        assert normalized.shape == covariates.shape

        # 验证没有 NaN/Inf
        assert not np.isnan(normalized).any()
        assert not np.isinf(normalized).any()

    def test_normalize_unknown_method(self, builder, sample_price_data):
        """测试未知标准化方法"""
        covariates = builder.build_covariates(prices=sample_price_data)

        with pytest.raises(ValueError, match="Unknown normalization method"):
            builder.normalize_covariates(covariates, method="unknown")


# =============================================================================
# 边界情况测试
# =============================================================================


class TestEdgeCases:
    """测试边界情况"""

    def test_minimal_valid_data(self, builder):
        """测试最小有效数据"""
        # 刚好达到最小长度
        data = np.random.randn(32).astype(np.float64)
        covariates = builder.build_covariates(prices=data)

        assert covariates.shape[0] == 32

    def test_constant_prices(self, builder):
        """测试恒定价格"""
        prices = np.ones(100) * 100.0
        covariates = builder.build_covariates(prices=prices)

        # 应该能处理恒定价格
        assert covariates.shape == (100, len(builder.enabled_features))

    def test_zero_volumes(self):
        """测试零成交量"""
        builder = ForecastCovariateBuilder(
            enabled_features=["volume_change"]
        )

        prices = np.linspace(100, 150, 100)
        volumes = np.zeros(100)

        covariates = builder.build_covariates(prices=prices, volumes=volumes)

        # 应该能处理零成交量
        assert covariates.shape == (100, 1)

    def test_very_long_data(self, builder):
        """测试超长数据"""
        data = np.random.randn(1000).astype(np.float64)
        covariates = builder.build_covariates(prices=data)

        assert covariates.shape[0] == 1000


# =============================================================================
# 性能测试
# =============================================================================


class TestPerformance:
    """性能测试"""

    def test_build_covariates_performance(self, builder):
        """测试协变量构建性能"""
        import time

        # 生成大量数据
        data = np.random.randn(10000).astype(np.float64)

        start = time.time()
        covariates = builder.build_covariates(prices=data)
        elapsed = time.time() - start

        # 应该在合理时间内完成
        assert elapsed < 5.0
        assert covariates.shape[0] == 10000


# =============================================================================
# 集成测试
# =============================================================================


class TestIntegration:
    """集成测试"""

    def test_full_pipeline(self, builder, sample_price_data, sample_volume_data):
        """测试完整流程"""
        # 1. 构建协变量
        covariates = builder.build_covariates(
            prices=sample_price_data,
            volumes=sample_volume_data,
        )

        # 2. 验证协变量
        validation_result = builder.validate_covariates(covariates)
        assert validation_result["is_valid"] is True

        # 3. 标准化协变量
        normalized = builder.normalize_covariates(covariates, method="standard")
        assert normalized.shape == covariates.shape

    def test_with_dataframe(self, builder):
        """测试从 DataFrame 构建"""
        df = pd.DataFrame({
            "close": np.linspace(100, 150, 100),
            "volume": np.random.randn(100) * 100000 + 1000000,
        })

        covariates = builder.build_covariates(
            prices=df["close"].values,
            volumes=df["volume"].values,
        )

        assert covariates.shape[0] == 100
        assert covariates.shape[1] == len(builder.enabled_features)
