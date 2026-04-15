# TimesFM 股价预测集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有股票分析系统中集成 Google TimesFM 模型，提供未来 60 天股价预测作为辅助决策参考

**Architecture:**
- 新增 TimesFMService 服务层，封装模型加载和预测逻辑
- 在 StockAnalysisPipeline 中集成预测调用，非侵入式注入结果
- 通过配置管理支持功能开关和参数调整
- 更新报告模板展示预测结果

**Tech Stack:**
- timesfm>=2.5.0 (Google TimesFM 模型)
- torch>=2.0.0 (PyTorch 后端)
- numpy (数据处理)
- pytest (测试)

---

## 文件结构

### 新建文件
```
src/services/timesfm_service.py          # TimesFM 服务封装
src/schemas/forecast_schema.py           # 预测结果数据结构
templates/forecast_section.zh.jinja2    # 中文报告模板
templates/forecast_section.en.jinja2    # 英文报告模板
templates/forecast_table.zh.jinja2      # 中文数据表格模板
templates/forecast_table.en.jinja2      # 英文数据表格模板
tests/test_timesfm_service.py           # 服务单元测试
tests/test_forecast_schema.py           # Schema 测试
```

### 修改文件
```
src/services/analysis_service.py        # 集成预测调用
src/core/pipeline.py                    # 注入预测结果
src/core/config_registry.py             # 添加配置字段
requirements.txt                        # 添加依赖
.env.example                            # 添加环境变量示例
docs/CHANGELOG.md                       # 更新变更日志
README.md                               # 更新文档
```

---

## Task 1: 添加依赖到 requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 添加 TimesFM 和 PyTorch 依赖**

在 requirements.txt 末尾添加：

```txt
# TimesFM AI 预测
timesfm>=2.5.0
torch>=2.0.0
```

- [ ] **Step 2: 验证依赖格式正确**

运行：`python -m pip check`
预期：无依赖冲突警告

- [ ] **Step 3: 提交变更**

```bash
git add requirements.txt
git commit -m "feat(timesfm): add timesfm and torch dependencies"
```

---

## Task 2: 创建预测结果 Schema

**Files:**
- Create: `src/schemas/forecast_schema.py`
- Test: `tests/test_forecast_schema.py`

- [ ] **Step 1: 创建 forecast_schema.py 文件**

创建 `src/schemas/forecast_schema.py`:

```python
# -*- coding: utf-8 -*-
"""
TimesFM 预测结果数据结构
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import numpy as np


@dataclass
class ForecastResult:
    """TimesFM 预测结果"""

    stock_code: str
    stock_name: str
    current_price: float
    prediction_date: datetime

    # 预测数据
    point_forecast: np.ndarray  # shape: (horizon,)
    quantile_forecast: np.ndarray  # shape: (horizon, 10)

    # 统计信息
    min_predicted: float
    max_predicted: float
    median_predicted: float
    trend_direction: str  # "up" / "down" / "sideways"

    # 元数据
    context_length: int
    horizon: int
    model_version: str
    generated_at: datetime

    def get_confidence_interval(self, confidence: float = 0.8) -> tuple:
        """
        获取指定置信区间

        Args:
            confidence: 置信水平（默认 0.8 = 80%）

        Returns:
            (lower_bound, upper_bound) 数组
        """
        if confidence == 0.8:
            # 80% 置信区间 = 10% - 90% 分位数
            lower = self.quantile_forecast[:, 0]  # 10%
            upper = self.quantile_forecast[:, 9]  # 90%
        elif confidence == 0.6:
            # 60% 置信区间 = 20% - 80% 分位数
            lower = self.quantile_forecast[:, 1]
            upper = self.quantile_forecast[:, 8]
        else:
            # 默认 80%
            lower = self.quantile_forecast[:, 0]
            upper = self.quantile_forecast[:, 9]
        return lower, upper

    def to_dict(self) -> dict:
        """转换为字典格式（用于 JSON 序列化）"""
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "current_price": float(self.current_price),
            "prediction_date": self.prediction_date.isoformat(),
            "point_forecast": self.point_forecast.tolist(),
            "quantile_forecast": self.quantile_forecast.tolist(),
            "min_predicted": float(self.min_predicted),
            "max_predicted": float(self.max_predicted),
            "median_predicted": float(self.median_predicted),
            "trend_direction": self.trend_direction,
            "context_length": self.context_length,
            "horizon": self.horizon,
            "model_version": self.model_version,
            "generated_at": self.generated_at.isoformat(),
        }

    def __post_init__(self):
        """初始化后验证"""
        # 验证数组形状
        assert self.point_forecast.shape[0] == self.horizon, \
            f"point_forecast length {self.point_forecast.shape[0]} != horizon {self.horizon}"
        assert self.quantile_forecast.shape == (self.horizon, 10), \
            f"quantile_forecast shape {self.quantile_forecast.shape} != ({self.horizon}, 10)"

        # 验证趋势方向
        assert self.trend_direction in ["up", "down", "sideways"], \
            f"Invalid trend_direction: {self.trend_direction}"
```

- [ ] **Step 2: 创建测试文件**

创建 `tests/test_forecast_schema.py`:

```python
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
```

- [ ] **Step 3: 运行测试验证**

运行：`pytest tests/test_forecast_schema.py -v`
预期：所有测试通过

- [ ] **Step 4: 提交变更**

```bash
git add src/schemas/forecast_schema.py tests/test_forecast_schema.py
git commit -m "feat(timesfm): add ForecastResult schema with tests"
```

---

## Task 3: 实现 TimesFM 服务层

**Files:**
- Create: `src/services/timesfm_service.py`
- Test: `tests/test_timesfm_service.py`

- [ ] **Step 1: 创建 timesfm_service.py 文件**

创建 `src/services/timesfm_service.py`:

```python
# -*- coding: utf-8 -*-
"""
TimesFM 服务层

职责：
1. 懒加载 TimesFM 模型
2. 提供预测接口
3. 数据预处理和后处理
"""

import logging
import threading
from typing import Optional, List
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)


class TimesFMServiceError(Exception):
    """TimesFM 服务异常基类"""
    pass


class ModelNotLoadedError(TimesFMServiceError):
    """模型未加载异常"""
    pass


class InsufficientDataError(TimesFMServiceError):
    """数据不足异常"""
    pass


class TimesFMService:
    """TimesFM 预测服务"""

    def __init__(
        self,
        model_id: str = "google/timesfm-2.5-200m-pytorch",
        max_context: int = 0,
        max_horizon: int = 60,
        device: str = "auto",
        use_quantile_head: bool = True,
        cache_dir: Optional[str] = None,
    ):
        """
        初始化服务（懒加载模型）

        Args:
            model_id: Hugging Face 模型 ID
            max_context: 最大上下文长度（0 = 自适应）
            max_horizon: 最大预测天数
            device: 推理设备（auto/cpu/cuda）
            use_quantile_head: 是否使用连续分位数头
            cache_dir: 模型缓存目录
        """
        self.model_id = model_id
        self.max_context = max_context
        self.max_horizon = max_horizon
        self.device = device
        self.use_quantile_head = use_quantile_head
        self.cache_dir = cache_dir

        # 懒加载
        self._model: Optional[object] = None
        self._lock = threading.Lock()
        self._is_loaded = False

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self._is_loaded and self._model is not None

    def load_model(self) -> None:
        """
        加载 TimesFM 模型到内存

        线程安全的懒加载
        """
        if self._is_loaded:
            return

        with self._lock:
            # 双检锁
            if self._is_loaded:
                return

            try:
                import timesfm

                logger.info(f"Loading TimesFM model: {self.model_id}")

                # 设置 torch 精度（如果可用）
                try:
                    import torch
                    torch.set_float32_matmul_precision("high")
                except ImportError:
                    logger.warning("PyTorch not available, skipping precision setting")

                # 加载模型
                self._model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                    self.model_id,
                    cache_dir=self.cache_dir,
                )

                # 编译模型
                import timesfm as tfm
                self._model.compile(
                    tfm.ForecastConfig(
                        max_context=self.max_context if self.max_context > 0 else 1024,
                        max_horizon=self.max_horizon,
                        normalize_inputs=True,
                        use_continuous_quantile_head=self.use_quantile_head,
                        force_flip_invariance=True,
                        infer_is_positive=True,  # 股价为正数
                        fix_quantile_crossing=True,
                    )
                )

                self._is_loaded = True
                logger.info("TimesFM model loaded successfully")

            except ImportError as e:
                logger.error(f"TimesFM not installed: {e}")
                raise TimesFMServiceError("TimesFM not installed. Run: pip install timesfm[torch]")
            except Exception as e:
                logger.error(f"Failed to load TimesFM model: {e}")
                raise TimesFMServiceError(f"Failed to load model: {e}")

    def unload_model(self) -> None:
        """卸载模型释放内存"""
        with self._lock:
            if self._model is not None:
                del self._model
                self._model = None
                self._is_loaded = False
                logger.info("TimesFM model unloaded")

    def predict(
        self,
        prices: np.ndarray,
        horizon: int = 60,
        context_length: Optional[int] = None,
    ) -> "ForecastResult":
        """
        执行预测

        Args:
            prices: 历史价格序列（1D numpy array）
            horizon: 预测天数
            context_length: 上下文长度（None = 自适应）

        Returns:
            ForecastResult 对象

        Raises:
            ModelNotLoadedError: 模型未加载
            InsufficientDataError: 数据不足
        """
        from src.schemas.forecast_schema import ForecastResult

        # 确保模型已加载
        if not self.is_available():
            self.load_model()

        # 验证输入
        if len(prices) < 10:
            raise InsufficientDataError(
                f"Insufficient data: {len(prices)} points. At least 10 required."
            )

        # 确定上下文长度
        if context_length is None:
            # 自适应：使用最多可用数据，但不超过 max_context
            if self.max_context > 0:
                context_length = min(len(prices), self.max_context)
            else:
                context_length = min(len(prices), 1024)  # 默认最大 1024
        else:
            context_length = min(context_length, len(prices))

        # 提取上下文数据
        context_prices = prices[-context_length:]

        try:
            # 执行预测
            point_forecast, quantile_forecast = self._model.forecast(
                horizon=min(horizon, self.max_horizon),
                inputs=[context_prices],
            )

            # 提取结果（TimesFM 返回 batch，我们只用第一个）
            point_forecast = point_forecast[0]  # (horizon,)
            quantile_forecast = quantile_forecast[0]  # (horizon, 10)

            # 计算统计信息
            min_predicted = float(np.min(point_forecast))
            max_predicted = float(np.max(point_forecast))
            median_predicted = float(np.median(point_forecast))

            # 判断趋势方向
            first_5_avg = np.mean(point_forecast[:5])
            last_5_avg = np.mean(point_forecast[-5:])
            change_pct = (last_5_avg - first_5_avg) / first_5_avg * 100

            if change_pct > 2:
                trend_direction = "up"
            elif change_pct < -2:
                trend_direction = "down"
            else:
                trend_direction = "sideways"

            # 构建结果（注意：stock_code 和 stock_name 需要调用者设置）
            result = ForecastResult(
                stock_code="",  # 由调用者设置
                stock_name="",  # 由调用者设置
                current_price=float(prices[-1]),
                prediction_date=datetime.now(),
                point_forecast=point_forecast,
                quantile_forecast=quantile_forecast,
                min_predicted=min_predicted,
                max_predicted=max_predicted,
                median_predicted=median_predicted,
                trend_direction=trend_direction,
                context_length=context_length,
                horizon=len(point_forecast),
                model_version="2.5",
                generated_at=datetime.now(),
            )

            return result

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise TimesFMServiceError(f"Prediction failed: {e}")

    def predict_batch(
        self,
        price_series_list: List[np.ndarray],
        horizon: int = 60,
    ) -> List["ForecastResult"]:
        """
        批量预测多只股票

        Args:
            price_series_list: 价格序列列表
            horizon: 预测天数

        Returns:
            ForecastResult 列表
        """
        results = []
        for prices in price_series_list:
            try:
                result = self.predict(prices, horizon=horizon)
                results.append(result)
            except TimesFMServiceError as e:
                logger.warning(f"Failed to predict one series: {e}")
                # 返回 None 占位，保持结果列表与输入列表对应
                results.append(None)
        return results
```

- [ ] **Step 2: 创建服务测试文件**

创建 `tests/test_timesfm_service.py`:

```python
# -*- coding: utf-8 -*-
"""测试 TimesFM 服务"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from src.services.timesfm_service import (
    TimesFMService,
    ModelNotLoadedError,
    InsufficientDataError,
    TimesFMServiceError,
)


@pytest.fixture
def mock_timesfm():
    """Mock TimesFM 模块"""
    with patch("src.services.timesfm_service.timesfm") as mock:
        # Mock model class
        mock_model = MagicMock()
        mock.TimesFM_2p5_200M_torch.from_pretrained.return_value = mock_model
        mock.ForecastConfig = MagicMock

        # Mock forecast result
        mock_model.forecast.return_value = (
            np.array([[150, 151, 152, 153, 154, 155]]),  # point_forecast
            np.array([[[140] * 10, [141] * 10, [142] * 10, [143] * 10, [144] * 10, [145] * 10]]).T,
        )
        yield mock


def test_service_initialization():
    """测试服务初始化"""
    service = TimesFMService(
        model_id="test-model",
        max_context=512,
        max_horizon=60,
    )
    assert service.model_id == "test-model"
    assert service.max_context == 512
    assert service.max_horizon == 60
    assert not service.is_available()


def test_model_loading(mock_timesfm):
    """测试模型加载"""
    service = TimesFMService()
    service.load_model()
    assert service.is_available()


def test_model_loading_import_error():
    """测试 TimesFM 未安装场景"""
    with patch("src.services.timesfm_service.timesfm", side_effect=ImportError("No module")):
        service = TimesFMService()
        with pytest.raises(TimesFMServiceError):
            service.load_model()


def test_predict_with_mock(mock_timesfm):
    """测试预测（使用 mock）"""
    service = TimesFMService()
    service.load_model()

    # 生成测试数据
    prices = np.array([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])

    result = service.predict(prices, horizon=6)

    assert result.current_price == 109.0
    assert result.horizon == 6
    assert result.trend_direction in ["up", "down", "sideways"]


def test_predict_insufficient_data(mock_timesfm):
    """测试数据不足场景"""
    service = TimesFMService()
    service.load_model()

    # 只有 5 个数据点
    prices = np.array([100, 101, 102, 103, 104])

    with pytest.raises(InsufficientDataError):
        service.predict(prices)


def test_predict_without_model_loading():
    """测试未加载模型时预测"""
    service = TimesFMService()
    prices = np.ones(100)

    # 应该自动加载模型
    with patch("src.services.timesfm_service.timesfm") as mock_timesfm:
        mock_model = MagicMock()
        mock_timesfm.TimesFM_2p5_200M_torch.from_pretrained.return_value = mock_model
        mock_timesfm.ForecastConfig = MagicMock
        mock_model.forecast.return_value = (
            np.array([[150] * 60]),
            np.array([[[140] * 10] * 60]).T,
        )

        result = service.predict(prices)
        assert result is not None


def test_adaptive_context_length(mock_timesfm):
    """测试自适应上下文长度"""
    service = TimesFMService(max_context=0)  # 自适应模式

    # 短序列
    short_prices = np.ones(50)
    service.load_model()

    # 应该使用全部 50 个点
    with patch.object(service._model, "forecast") as mock_forecast:
        mock_forecast.return_value = (
            np.array([[150] * 60]),
            np.array([[[140] * 10] * 60]).T,
        )
        service.predict(short_prices)

        # 验证使用了正确的上下文长度
        call_args = mock_forecast.call_args
        inputs = call_args[1]["inputs"]
        assert len(inputs[0]) == 50


def test_trend_direction_calculation():
    """测试趋势方向计算"""
    service = TimesFMService()

    # 上涨趋势
    assert service._calculate_trend(np.array([100, 102, 104, 106, 108, 110])) == "up"

    # 下跌趋势
    assert service._calculate_trend(np.array([110, 108, 106, 104, 102, 100])) == "down"

    # 震荡
    assert service._calculate_trend(np.array([100, 101, 100, 101, 100, 101])) == "sideways"
```

- [ ] **Step 3: 添加趋势计算辅助方法**

在 `src/services/timesfm_service.py` 的 `TimesFMService` 类中添加：

```python
    def _calculate_trend(self, forecast: np.ndarray) -> str:
        """
        计算预测趋势方向

        Args:
            forecast: 预测序列

        Returns:
            "up" / "down" / "sideways"
        """
        if len(forecast) < 10:
            # 数据太少，比较首尾
            first_avg = forecast[0]
            last_avg = forecast[-1]
        else:
            # 比较前 5 个和后 5 个的平均值
            first_avg = np.mean(forecast[:5])
            last_avg = np.mean(forecast[-5:])

        change_pct = (last_avg - first_avg) / first_avg * 100

        if change_pct > 2:
            return "up"
        elif change_pct < -2:
            return "down"
        else:
            return "sideways"
```

并在 `predict` 方法中替换趋势计算逻辑：

```python
        # 判断趋势方向
        trend_direction = self._calculate_trend(point_forecast)
```

- [ ] **Step 4: 运行测试**

运行：`pytest tests/test_timesfm_service.py -v`
预期：所有测试通过（需要 TimesFM 模块，或使用 mock）

- [ ] **Step 5: 提交变更**

```bash
git add src/services/timesfm_service.py tests/test_timesfm_service.py
git commit -m "feat(timesfm): implement TimesFMService with lazy loading and prediction"
```

---

## Task 4: 添加配置字段

**Files:**
- Modify: `src/core/config_registry.py`
- Modify: `.env.example`

- [ ] **Step 1: 在 config_registry.py 中添加配置**

在 `src/core/config_registry.py` 的适当位置添加：

```python
# TimesFM AI 预测配置
ConfigRegistry.register_field("ai_forecast", {
    "TIMESFM_ENABLED": {
        "type": "boolean",
        "default": False,
        "label": "启用 AI 预测",
        "description": "在分析报告中包含 TimesFM 模型预测",
        "category": "ai_forecast",
    },
    "TIMESFM_MODEL_ID": {
        "type": "string",
        "default": "google/timesfm-2.5-200m-pytorch",
        "label": "模型 ID",
        "description": "Hugging Face 模型标识",
        "category": "ai_forecast",
    },
    "TIMESFM_MAX_CONTEXT": {
        "type": "integer",
        "default": 0,
        "label": "最大上下文长度",
        "description": "0 = 自适应，最大 16384",
        "category": "ai_forecast",
        "min": 0,
        "max": 16384,
    },
    "TIMESFM_MAX_HORIZON": {
        "type": "integer",
        "default": 60,
        "label": "最大预测天数",
        "description": "单次预测的最大天数",
        "category": "ai_forecast",
        "min": 1,
        "max": 365,
    },
    "TIMESFM_CACHE_DIR": {
        "type": "string",
        "default": None,
        "label": "模型缓存目录",
        "description": "留空使用默认 Hugging Face 缓存",
        "category": "ai_forecast",
        "optional": True,
    },
    "TIMESFM_DEVICE": {
        "type": "string",
        "default": "auto",
        "label": "推理设备",
        "description": "auto/cpu/cuda",
        "category": "ai_forecast",
        "enum": ["auto", "cpu", "cuda"],
    },
    "TIMESFM_USE_QUANTILE_HEAD": {
        "type": "boolean",
        "default": True,
        "label": "使用连续分位数头",
        "description": "提供更准确的预测区间",
        "category": "ai_forecast",
    },
})
```

- [ ] **Step 2: 在 .env.example 中添加环境变量**

在 `.env.example` 末尾添加：

```bash
# ===================================
# TimesFM AI 预测配置
# ===================================
# 是否启用 TimesFM 预测（默认 false）
TIMESFM_ENABLED=false
# 模型 ID（Hugging Face 模型标识）
TIMESFM_MODEL_ID=google/timesfm-2.5-200m-pytorch
# 最大上下文长度（0 = 自适应，最大 16384）
TIMESFM_MAX_CONTEXT=0
# 最大预测天数（默认 60）
TIMESFM_MAX_HORIZON=60
# 模型缓存目录（留空使用默认）
# TIMESFM_CACHE_DIR=/path/to/cache
# 推理设备（auto/cpu/cuda）
TIMESFM_DEVICE=auto
# 是否使用连续分位数头（推荐开启）
TIMESFM_USE_QUANTILE_HEAD=true
```

- [ ] **Step 3: 验证配置字段可读取**

运行：`python -c "from src.core.config_registry import ConfigRegistry; print(ConfigRegistry.get_field('TIMESFM_ENABLED'))"`
预期：返回配置字典

- [ ] **Step 4: 提交变更**

```bash
git add src/core/config_registry.py .env.example
git commit -m "feat(timesfm): add TimesFM configuration fields"
```

---

## Task 5: 在分析服务中集成预测

**Files:**
- Modify: `src/services/analysis_service.py`

- [ ] **Step 1: 在 AnalysisService 中添加预测方法**

在 `src/services/analysis_service.py` 的 `AnalysisService` 类中添加：

```python
    def _run_timesfm_forecast(
        self,
        stock_code: str,
        stock_name: str,
        prices: np.ndarray,
    ) -> Optional["ForecastResult"]:
        """
        运行 TimesFM 预测

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            prices: 历史价格序列

        Returns:
            ForecastResult 或 None（预测失败时）
        """
        from src.config import get_config
        from src.services.timesfm_service import TimesFMService, TimesFMServiceError

        config = get_config()

        # 检查是否启用
        if not config.get("TIMESFM_ENABLED", False):
            return None

        try:
            # 创建或获取服务实例（单例模式）
            if not hasattr(self, "_timesfm_service"):
                self._timesfm_service = TimesFMService(
                    model_id=config.get("TIMESFM_MODEL_ID", "google/timesfm-2.5-200m-pytorch"),
                    max_context=config.get("TIMESFM_MAX_CONTEXT", 0),
                    max_horizon=config.get("TIMESFM_MAX_HORIZON", 60),
                    device=config.get("TIMESFM_DEVICE", "auto"),
                    use_quantile_head=config.get("TIMESFM_USE_QUANTILE_HEAD", True),
                    cache_dir=config.get("TIMESFM_CACHE_DIR"),
                )

            # 执行预测
            result = self._timesfm_service.predict(
                prices=prices,
                horizon=config.get("TIMESFM_MAX_HORIZON", 60),
            )

            # 设置股票信息
            result.stock_code = stock_code
            result.stock_name = stock_name

            return result

        except TimesFMServiceError as e:
            logger.warning(f"TimesFM prediction failed for {stock_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in TimesFM prediction for {stock_code}: {e}")
            return None
```

- [ ] **Step 2: 在 _build_analysis_response 中注入预测结果**

修改 `src/services/analysis_service.py` 的 `_build_analysis_response` 方法，在返回前添加预测结果：

```python
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
        # ... 现有代码 ...

        # 尝试获取 TimesFM 预测
        forecast_result = None
        if hasattr(result, "prices") and result.prices is not None:
            try:
                forecast_result = self._run_timesfm_forecast(
                    stock_code=result.code,
                    stock_name=stock_name,
                    prices=result.prices,
                )
            except Exception as e:
                logger.warning(f"Failed to get TimesFM forecast: {e}")

        # 构建报告结构
        report = {
            "meta": {
                "query_id": query_id,
                "stock_code": result.code,
                "stock_name": stock_name,
                "report_type": report_type,
                # ... 现有字段 ...
            },
            # ... 现有字段 ...
            "forecast": forecast_result.to_dict() if forecast_result else None,
        }

        return report
```

- [ ] **Step 3: 测试集成**

运行：`python -c "from src.services.analysis_service import AnalysisService; s = AnalysisService(); print(hasattr(s, '_run_timesfm_forecast'))"`
预期：True

- [ ] **Step 4: 提交变更**

```bash
git add src/services/analysis_service.py
git commit -m "feat(timesfm): integrate TimesFM prediction into analysis service"
```

---

## Task 6: 创建报告模板

**Files:**
- Create: `templates/forecast_section.zh.jinja2`
- Create: `templates/forecast_section.en.jinja2`
- Create: `templates/forecast_table.zh.jinja2`
- Create: `templates/forecast_table.en.jinja2`

- [ ] **Step 1: 创建中文预测章节模板**

创建 `templates/forecast_section.zh.jinja2`:

```jinja2
{% if forecast %}
## AI 预测参考

> ⚠️ **免责声明**: 以下预测由 AI 模型生成，仅供参考，不构成投资建议。股票市场具有高度不确定性，请结合多方面因素进行综合判断。

### 预测概要

- **预测周期**: 未来 {{ forecast.horizon }} 个交易日
- **当前价格**: {{ "¥%.2f"|format(forecast.current_price) if forecast.current_price < 1000 else "¥%.2f"|format(forecast.current_price) }}
- **预测中位数**: {{ "¥%.2f"|format(forecast.median_predicted) }} ({{ "%.1f%%"|format((forecast.median_predicted - forecast.current_price) / forecast.current_price * 100) }})
- **预测区间**: {{ "¥%.2f"|format(forecast.min_predicted) }} - {{ "¥%.2f"|format(forecast.max_predicted) }} (80% 置信区间)
- **趋势判断**:
  {% if forecast.trend_direction == "up" %}
  ↗️ **上涨**
  {% elif forecast.trend_direction == "down" %}
  ↘️ **下跌**
  {% else %}
  ➡️ **震荡**
  {% endif %}

{% if show_forecast_table %}
{% include "forecast_table.zh.jinja2" %}
{% endif %}

{% endif %}
```

- [ ] **Step 2: 创建英文预测章节模板**

创建 `templates/forecast_section.en.jinja2`:

```jinja2
{% if forecast %}
## AI Forecast Reference

> ⚠️ **Disclaimer**: The following forecast is generated by an AI model and is for reference only. It does not constitute investment advice. Stock markets are highly uncertain; please consider multiple factors before making decisions.

### Forecast Summary

- **Forecast Period**: Next {{ forecast.horizon }} trading days
- **Current Price**: ${{ "%.2f"|format(forecast.current_price) }}
- **Median Forecast**: ${{ "%.2f"|format(forecast.median_predicted) }} ({{ "%.1f%%"|format((forecast.median_predicted - forecast.current_price) / forecast.current_price * 100) }})
- **Forecast Range**: ${{ "%.2f"|format(forecast.min_predicted) }} - ${{ "%.2f"|format(forecast.max_predicted) }} (80% confidence interval)
- **Trend**:
  {% if forecast.trend_direction == "up" %}
  ↗️ **Upward**
  {% elif forecast.trend_direction == "down" %}
  ↘️ **Downward**
  {% else %}
  ➡️ **Sideways**
  {% endif %}

{% if show_forecast_table %}
{% include "forecast_table.en.jinja2" %}
{% endif %}

{% endif %}
```

- [ ] **Step 3: 创建中文数据表格模板**

创建 `templates/forecast_table.zh.jinja2`:

```jinja2
### 详细预测数据

| 日期 | 中位数预测 | 10% 分位数 | 90% 分位数 |
|------|-----------|-----------|-----------|
{% for i in range(0, forecast.horizon, 10) %}
{% set end_idx = (i + 10) | int %}
{% if end_idx > forecast.horizon %}
{% set end_idx = forecast.horizon %}
{% endif %}
| T+{{ i + 1 }}{% if end_idx > i + 1 %} - T+{{ end_idx }}{% endif %} | {{ "¥%.2f"|format(forecast.point_forecast[i]) }}{% if end_idx > i + 1 %} - {{ "¥%.2f"|format(forecast.point_forecast[end_idx - 1]) }}{% endif %} | {{ "¥%.2f"|format(forecast.quantile_forecast[i][0]) }}{% if end_idx > i + 1 %} - {{ "¥%.2f"|format(forecast.quantile_forecast[end_idx - 1][0]) }}{% endif %} | {{ "¥%.2f"|format(forecast.quantile_forecast[i][9]) }}{% if end_idx > i + 1 %} - {{ "¥%.2f"|format(forecast.quantile_forecast[end_idx - 1][9]) }}{% endif %} |
{% endfor %}
```

- [ ] **Step 4: 创建英文数据表格模板**

创建 `templates/forecast_table.en.jinja2`:

```jinja2
### Detailed Forecast Data

| Date | Median Forecast | 10th Percentile | 90th Percentile |
|------|----------------|-----------------|-----------------|
{% for i in range(0, forecast.horizon, 10) %}
{% set end_idx = (i + 10) | int %}
{% if end_idx > forecast.horizon %}
{% set end_idx = forecast.horizon %}
{% endif %}
| T+{{ i + 1 }}{% if end_idx > i + 1 %} - T+{{ end_idx }}{% endif %} | ${{ "%.2f"|format(forecast.point_forecast[i]) }}{% if end_idx > i + 1 %} - ${{ "%.2f"|format(forecast.point_forecast[end_idx - 1]) }}{% endif %} | ${{ "%.2f"|format(forecast.quantile_forecast[i][0]) }}{% if end_idx > i + 1 %} - ${{ "%.2f"|format(forecast.quantile_forecast[end_idx - 1][0]) }}{% endif %} | ${{ "%.2f"|format(forecast.quantile_forecast[i][9]) }}{% if end_idx > i + 1 %} - ${{ "%.2f"|format(forecast.quantile_forecast[end_idx - 1][9]) }}{% endif %} |
{% endfor %}
```

- [ ] **Step 5: 提交变更**

```bash
git add templates/
git commit -m "feat(timesfm): add forecast report templates (zh/en)"
```

---

## Task 7: 更新文档和变更日志

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: 更新 CHANGELOG.md**

在 `docs/CHANGELOG.md` 的 `[Unreleased]` 部分添加：

```markdown
- [新功能] 集成 Google TimesFM 模型，提供未来 60 天股价预测作为辅助决策参考
- [新功能] 新增 TimesFMService 服务层，支持懒加载和自适应上下文长度
- [新功能] 添加预测结果配置管理（TIMESFM_ENABLED 等）
- [新功能] 支持中英文预测报告模板
```

- [ ] **Step 2: 更新 README.md**

在 `README.md` 的适当位置添加：

```markdown
### AI 预测（Beta）

系统集成了 Google TimesFM 模型，提供未来 60 天的股价预测作为辅助决策参考。

**启用方式**：
```bash
# .env
TIMESFM_ENABLED=true
```

**特点**：
- 零样本预测，无需训练
- 提供 80% 置信区间
- 自适应历史数据长度
- 非侵入式集成，失败不影响主分析流程

**免责声明**: 预测仅供参考，不构成投资建议。
```

- [ ] **Step 3: 提交变更**

```bash
git add docs/CHANGELOG.md README.md
git commit -m "docs(timesfm): update changelog and README for TimesFM integration"
```

---

## Task 8: 端到端集成测试

**Files:**
- Test: 手动验证

- [ ] **Step 1: 安装依赖**

运行：`pip install -e .[torch]`
预期：成功安装 timesfm 和 torch

- [ ] **Step 2: 启用 TimesFM 并运行测试**

在 `.env` 中设置：
```bash
TIMESFM_ENABLED=true
```

运行：`python main.py --stocks 600519 --dry-run`
预期：分析报告中包含 AI 预测章节

- [ ] **Step 3: 验证禁用功能**

在 `.env` 中设置：
```bash
TIMESFM_ENABLED=false
```

运行：`python main.py --stocks 600519 --dry-run`
预期：分析报告中不包含 AI 预测章节

- [ ] **Step 4: 运行单元测试**

运行：`pytest tests/test_timesfm_service.py tests/test_forecast_schema.py -v`
预期：所有测试通过

- [ ] **Step 5: 验证 CI 通过**

运行：`./scripts/ci_gate.sh`
预期：所有检查通过

- [ ] **Step 6: 提交最终变更**

```bash
git add -A
git commit -m "test(timesfm): add integration tests and validation"
```

---

## 验收标准

完成所有任务后，以下标准应全部满足：

- [ ] TimesFM 2.5 模型成功加载
- [ ] 能够生成 60 天股价预测
- [ ] 预测结果正确集成到分析报告中
- [ ] 支持 `TIMESFM_ENABLED=false` 禁用功能
- [ ] 预测失败不影响主分析流程
- [ ] 中英文报告正确渲染预测章节
- [ ] 单元测试覆盖率 > 80%
- [ ] CI 检查全部通过
- [ ] 文档已更新（CHANGELOG、README）

---

## 参考资料

- [TimesFM GitHub](https://github.com/google-research/timesfm)
- [设计文档](../specs/2026-04-15-timesfm-integration-design.md)
- [项目 AGENTS.md](../../../AGENTS.md)
