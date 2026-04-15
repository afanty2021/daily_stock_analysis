# -*- coding: utf-8 -*-
"""
===================================
TimesFM 服务测试
===================================

测试 TimesFMService 的各项功能：
- 模型懒加载
- 数据验证
- 预测功能
- 批量预测
- 趋势计算
- 异常处理
"""

from unittest.mock import Mock, MagicMock, patch, PropertyMock
from datetime import datetime, timedelta
import pytest
import numpy as np
import pandas as pd

from src.services.timesfm_service import (
    TimesFMService,
    TimesFMServiceError,
    ModelNotLoadedError,
    InsufficientDataError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_timesfm_module():
    """Mock timesfm 模块 - 使用类级别的 mock"""
    import sys

    # 创建 mock 模块
    mock_model = MagicMock()
    mock_timesfm_class = MagicMock(return_value=mock_model)

    mock_timesfm = MagicMock()
    mock_timesfm.TimesFm = mock_timesfm_class

    # 临时添加到 sys.modules
    original_modules = sys.modules.copy()
    sys.modules['timesfm'] = mock_timesfm

    yield mock_timesfm, mock_model

    # 恢复原始模块
    sys.modules.clear()
    sys.modules.update(original_modules)


@pytest.fixture
def sample_time_series_data():
    """生成示例时间序列数据"""
    np.random.seed(42)
    n_points = 300
    # 生成带有趋势和噪声的数据
    trend = np.linspace(100, 150, n_points)
    noise = np.random.randn(n_points) * 5
    data = trend + noise
    return data.astype(np.float32)


@pytest.fixture
def sample_dataframe():
    """生成示例 DataFrame"""
    np.random.seed(42)
    n_points = 300
    dates = pd.date_range(end=datetime.now(), periods=n_points, freq="D")
    values = np.linspace(100, 150, n_points) + np.random.randn(n_points) * 5

    return pd.DataFrame({
        "date": dates,
        "close": values,
    })


@pytest.fixture
def service():
    """创建服务实例（不加载模型）"""
    return TimesFMService(
        context_len=256,
        horizon_len=32,
        backend="cpu",
    )


# =============================================================================
# 服务初始化测试
# =============================================================================


class TestTimesFMServiceInit:
    """测试服务初始化"""

    def test_init_default_params(self):
        """测试默认参数初始化"""
        service = TimesFMService()
        assert service.context_len == 256
        assert service.horizon_len == 32
        assert service.backend == "cpu"
        assert service.model_path is None
        assert not service.is_loaded()

    def test_init_custom_params(self):
        """测试自定义参数初始化"""
        service = TimesFMService(
            context_len=512,
            horizon_len=64,
            backend="gpu",
            model_path="/path/to/model",
        )
        assert service.context_len == 512
        assert service.horizon_len == 64
        assert service.backend == "gpu"
        assert service.model_path == "/path/to/model"


# =============================================================================
# 模型加载测试
# =============================================================================


class TestModelLoading:
    """测试模型加载"""

    def test_lazy_loading_on_first_access(self, service, mock_timesfm_module):
        """测试首次访问时懒加载"""
        mock_timesfm, mock_model = mock_timesfm_module

        # 模拟预测结果
        mock_model.forecast.return_value = np.array([[1.0, 2.0, 3.0]])

        # 访问 model 属性应触发加载
        model = service.model
        assert model is not None
        assert service.is_loaded()

        # 验证模型被创建
        mock_timesfm.TimesFm.assert_called_once()

    def test_model_load_with_local_path(self, mock_timesfm_module):
        """测试从本地路径加载"""
        mock_timesfm, mock_model = mock_timesfm_module

        service = TimesFMService(model_path="/local/path/to/model")
        _ = service.model

        # 验证 load_from_checkpoint 被调用
        mock_model.load_from_checkpoint.assert_called_once_with("/local/path/to/model")

    def test_model_load_with_default_repo(self, mock_timesfm_module):
        """测试使用默认仓库加载"""
        mock_timesfm, mock_model = mock_timesfm_module

        service = TimesFMService()
        _ = service.model

        # 验证使用官方仓库
        mock_model.load_from_checkpoint.assert_called_once_with(
            repo_id="google/timesfm-1.0-200m"
        )

    def test_thread_safe_loading(self, service, mock_timesfm_module):
        """测试线程安全的加载"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = np.array([[1.0, 2.0]])

        # 模拟并发访问
        models = [service.model for _ in range(5)]

        # 验证只创建了一次
        assert mock_timesfm.TimesFm.call_count == 1
        assert all(m is not None for m in models)

    def test_unload_model(self, service, mock_timesfm_module):
        """测试卸载模型"""
        mock_timesfm, mock_model = mock_timesfm_module

        # 加载模型
        _ = service.model
        assert service.is_loaded()

        # 卸载模型
        service.unload()
        assert not service.is_loaded()


# =============================================================================
# 预测功能测试
# =============================================================================


class TestPredict:
    """测试预测功能"""

    def test_predict_basic(self, service, mock_timesfm_module, sample_time_series_data):
        """测试基本预测"""
        mock_timesfm, mock_model = mock_timesfm_module

        # 模拟预测结果
        expected_predictions = np.array([150.0, 151.0, 152.0, 153.0, 154.0])
        mock_model.forecast.return_value = (expected_predictions.reshape(1, -1),)

        result = service.predict(sample_time_series_data, horizon=5)

        # 验证结果结构
        assert "predictions" in result
        assert "trend" in result
        assert "metadata" in result

        # 验证预测值
        assert len(result["predictions"]) == 5
        assert result["predictions"] == expected_predictions.tolist()

        # 验证元数据
        assert result["metadata"]["horizon_len"] == 5
        assert result["metadata"]["context_len"] == 256

    def test_predict_with_custom_horizon(self, service, mock_timesfm_module):
        """测试自定义预测长度"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0] * 10]),)

        data = np.random.randn(300).astype(np.float32)
        result = service.predict(data, horizon=10)

        assert len(result["predictions"]) == 10
        assert result["metadata"]["horizon_len"] == 10

    def test_predict_with_different_frequencies(self, service, mock_timesfm_module):
        """测试不同频率的预测"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0, 2.0]]),)

        data = np.random.randn(300).astype(np.float32)

        for freq in ["D", "H", "W", "M"]:
            result = service.predict(data, frequency=freq)
            assert result["metadata"]["frequency"] == freq

    def test_predict_adaptive_context(self, service, mock_timesfm_module):
        """测试自适应上下文长度"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0, 2.0]]),)

        # 短数据（小于默认上下文）
        short_data = np.random.randn(100).astype(np.float32)
        result = service.predict(short_data)

        assert result["metadata"]["context_len"] == 100
        assert result["metadata"]["input_length"] == 100

    def test_predict_trend_calculation(self, service, mock_timesfm_module):
        """测试趋势计算"""
        mock_timesfm, mock_model = mock_timesfm_module

        # 上升趋势
        up_trend = np.array([100, 102, 104, 106, 108])
        mock_model.forecast.return_value = (up_trend.reshape(1, -1),)

        data = np.random.randn(300).astype(np.float32)
        result = service.predict(data)

        trend = result["trend"]
        assert trend["direction"] == "up"
        assert trend["strength"] > 0
        assert trend["change_pct"] > 0
        assert trend["start_value"] == 100.0
        assert trend["end_value"] == 108.0

        # 下降趋势
        down_trend = np.array([108, 106, 104, 102, 100])
        mock_model.forecast.return_value = (down_trend.reshape(1, -1),)

        result = service.predict(data)
        assert result["trend"]["direction"] == "down"

    def test_predict_flat_trend(self, service, mock_timesfm_module):
        """测试平坦趋势"""
        mock_timesfm, mock_model = mock_timesfm_module

        flat_trend = np.array([100.0, 100.1, 99.9, 100.0, 100.0])
        mock_model.forecast.return_value = (flat_trend.reshape(1, -1),)

        data = np.random.randn(300).astype(np.float32)
        result = service.predict(data)

        assert result["trend"]["direction"] == "flat"
        assert abs(result["trend"]["change_pct"]) < 1.0


# =============================================================================
# 批量预测测试
# =============================================================================


class TestBatchPredict:
    """测试批量预测"""

    def test_batch_predict_success(self, service, mock_timesfm_module):
        """测试成功的批量预测"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0, 2.0]]),)

        data_list = [
            np.random.randn(300).astype(np.float32),
            np.random.randn(400).astype(np.float32),
            np.random.randn(500).astype(np.float32),
        ]

        results = service.batch_predict(data_list, horizon=2)

        assert len(results) == 3
        for result in results:
            assert "predictions" in result
            assert "trend" in result
            assert "error" not in result

    def test_batch_predict_with_errors(self, service, mock_timesfm_module):
        """测试批量预测中的错误处理"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0, 2.0]]),)

        data_list = [
            np.random.randn(300).astype(np.float32),  # 有效数据
            np.random.randn(10).astype(np.float32),   # 数据不足
            np.random.randn(400).astype(np.float32),  # 有效数据
        ]

        results = service.batch_predict(data_list, horizon=2)

        assert len(results) == 3
        # 第一个和第三个应该成功
        assert "error" not in results[0]
        assert "error" in results[1]  # 数据不足
        assert "error" not in results[2]

    def test_batch_predict_empty_list(self, service):
        """测试空列表批量预测"""
        results = service.batch_predict([])
        assert results == []


# =============================================================================
# DataFrame 预测测试
# =============================================================================


class TestPredictFromDataFrame:
    """测试从 DataFrame 预测"""

    def test_predict_from_dataframe_basic(
        self, service, mock_timesfm_module, sample_dataframe
    ):
        """测试基本的 DataFrame 预测"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0, 2.0]]),)

        result = service.predict_from_dataframe(
            sample_dataframe,
            value_column="close",
            date_column="date",
            horizon=2,
        )

        assert "predictions" in result
        assert len(result["predictions"]) == 2

    def test_predict_from_dataframe_invalid_column(self, service, sample_dataframe):
        """测试无效列名"""
        with pytest.raises(ValueError, match="Value column 'invalid' not found"):
            service.predict_from_dataframe(
                sample_dataframe,
                value_column="invalid",
                date_column="date",
            )

    def test_predict_from_dataframe_auto_infer_freq(
        self, service, mock_timesfm_module, sample_dataframe
    ):
        """测试自动推断频率"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0, 2.0]]),)

        result = service.predict_from_dataframe(
            sample_dataframe,
            value_column="close",
            date_column="date",
        )

        # 验证频率被推断
        assert "frequency" in result["metadata"]
        assert result["metadata"]["frequency"] in ["D", "H", "W", "M"]


# =============================================================================
# 数据验证测试
# =============================================================================


class TestDataValidation:
    """测试数据验证"""

    def test_empty_data(self, service):
        """测试空数据"""
        with pytest.raises(ValueError, match="Input data cannot be empty"):
            service.predict(np.array([]))

    def test_insufficient_data(self, service):
        """测试数据不足"""
        short_data = np.random.randn(10).astype(np.float32)

        with pytest.raises(InsufficientDataError):
            service.predict(short_data)

    def test_non_array_data(self, service):
        """测试非数组数据"""
        with pytest.raises(ValueError, match="Input data must be a numpy array"):
            service.predict([1, 2, 3, 4, 5])

    def test_data_with_nan(self, service, mock_timesfm_module):
        """测试包含 NaN 的数据（应警告但继续）"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0, 2.0]]),)

        data = np.array([1.0, 2.0, np.nan, 4.0, 5.0] * 60, dtype=np.float32)

        # 应该警告但不抛出异常
        result = service.predict(data)
        assert "predictions" in result

    def test_data_with_inf(self, service):
        """测试包含 Inf 的数据（应抛出异常）"""
        data = np.array([1.0, 2.0, np.inf, 4.0, 5.0] * 60, dtype=np.float32)

        with pytest.raises(ValueError, match="Input data contains infinite values"):
            service.predict(data)


# =============================================================================
# 趋势计算测试
# =============================================================================


class TestTrendCalculation:
    """测试趋势计算"""

    def test_calculate_trend_up(self, service):
        """测试上升趋势计算"""
        predictions = np.array([100, 105, 110, 115, 120])
        trend = service._calculate_trend(predictions)

        assert trend["direction"] == "up"
        assert trend["strength"] > 0
        assert trend["change_pct"] > 0
        assert trend["start_value"] == 100.0
        assert trend["end_value"] == 120.0

    def test_calculate_trend_down(self, service):
        """测试下降趋势计算"""
        predictions = np.array([120, 115, 110, 105, 100])
        trend = service._calculate_trend(predictions)

        assert trend["direction"] == "down"
        assert trend["strength"] > 0
        assert trend["change_pct"] < 0

    def test_calculate_trend_flat(self, service):
        """测试平坦趋势计算"""
        predictions = np.array([100.0, 100.1, 99.9, 100.0, 100.0])
        trend = service._calculate_trend(predictions)

        assert trend["direction"] == "flat"
        assert abs(trend["change_pct"]) < 1.0

    def test_calculate_trend_single_point(self, service):
        """测试单点趋势"""
        predictions = np.array([100.0])
        trend = service._calculate_trend(predictions)

        assert trend["direction"] == "flat"
        assert trend["strength"] == 0.0
        assert trend["start_value"] == 100.0
        assert trend["end_value"] == 100.0

    def test_calculate_trend_empty(self, service):
        """测试空趋势"""
        predictions = np.array([])
        trend = service._calculate_trend(predictions)

        assert trend["direction"] == "flat"
        assert trend["start_value"] == 0.0
        assert trend["end_value"] == 0.0


# =============================================================================
# 异常处理测试
# =============================================================================


class TestErrorHandling:
    """测试异常处理"""

    def test_import_error(self):
        """测试 timesfm 未安装时的错误"""
        # 使用 builtins.__import__ 来模拟导入失败
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "timesfm":
                raise ImportError("No module named 'timesfm'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            service = TimesFMService()

            with pytest.raises(TimesFMServiceError, match="timesfm package not installed"):
                _ = service.model

    def test_model_load_error(self):
        """测试模型加载失败"""
        # 使用实际的导入路径
        with patch("builtins.__import__") as mock_import:
            # 创建一个模拟的 timesfm 模块，但 TimesFm 初始化失败
            mock_timesfm = MagicMock()
            mock_timesfm.TimesFm.side_effect = Exception("Load failed")

            def import_side_effect(name, *args, **kwargs):
                if name == "timesfm":
                    return mock_timesfm
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect

            service = TimesFMService()

            with pytest.raises(TimesFMServiceError, match="Model loading failed"):
                _ = service.model

    def test_prediction_error(self, service, mock_timesfm_module):
        """测试预测失败"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.side_effect = Exception("Prediction failed")

        data = np.random.randn(300).astype(np.float32)

        with pytest.raises(TimesFMServiceError, match="Prediction failed"):
            service.predict(data)


# =============================================================================
# 自适应上下文测试
# =============================================================================


class TestAdaptiveContext:
    """测试自适应上下文"""

    def test_adaptive_context_short_data(self, service):
        """测试短数据的自适应"""
        data_length = 100
        context_len = service._adaptive_context_length(data_length)

        assert context_len == data_length

    def test_adaptive_context_sufficient_data(self, service):
        """测试充足数据的自适应"""
        data_length = 500
        context_len = service._adaptive_context_length(data_length)

        assert context_len == service.context_len

    def test_adaptive_context_exact_match(self, service):
        """测试精确匹配"""
        data_length = service.context_len
        context_len = service._adaptive_context_length(data_length)

        assert context_len == service.context_len


# =============================================================================
# 边界情况测试
# =============================================================================


class TestEdgeCases:
    """测试边界情况"""

    def test_minimal_valid_data(self, service, mock_timesfm_module):
        """测试最小有效数据"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0]]),)

        # 刚好达到最小长度
        data = np.random.randn(32).astype(np.float32)
        result = service.predict(data, horizon=1)

        assert "predictions" in result

    def test_very_long_prediction(self, service, mock_timesfm_module):
        """测试超长预测"""
        mock_timesfm, mock_model = mock_timesfm_module
        long_predictions = np.random.randn(256).astype(np.float32)
        mock_model.forecast.return_value = (long_predictions.reshape(1, -1),)

        data = np.random.randn(500).astype(np.float32)
        result = service.predict(data, horizon=256)

        assert len(result["predictions"]) == 256

    def test_zero_values(self, service, mock_timesfm_module):
        """测试全零值"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.zeros((1, 5)),)

        data = np.zeros(100, dtype=np.float32)
        result = service.predict(data, horizon=5)

        assert result["predictions"] == [0.0] * 5
        assert result["trend"]["direction"] == "flat"


# =============================================================================
# 性能测试
# =============================================================================


class TestPerformance:
    """性能测试"""

    def test_batch_predict_performance(self, service, mock_timesfm_module):
        """测试批量预测性能"""
        mock_timesfm, mock_model = mock_timesfm_module
        mock_model.forecast.return_value = (np.array([[1.0, 2.0]]),)

        # 生成大量数据
        data_list = [np.random.randn(300).astype(np.float32) for _ in range(100)]

        import time
        start = time.time()
        results = service.batch_predict(data_list, horizon=2)
        elapsed = time.time() - start

        assert len(results) == 100
        # 应该在合理时间内完成（mock 数据应该很快）
        assert elapsed < 5.0
