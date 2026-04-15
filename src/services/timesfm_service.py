# -*- coding: utf-8 -*-
"""
===================================
TimesFM 时间序列预测服务
===================================

职责：
1. 封装 TimesFM 模型加载和预测逻辑
2. 提供懒加载机制，避免启动时加载大型模型
3. 支持单股票和批量股票预测
4. 计算预测趋势和置信度
"""

import logging
import threading
from typing import List, Literal, Optional, Dict, Any

import numpy as np
import pandas as pd

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
    """
    TimesFM 时间序列预测服务

    特性：
    - 懒加载：首次调用时加载模型，避免启动时加载
    - 线程安全：使用锁确保模型只加载一次
    - 自适应上下文：根据数据长度自动调整上下文长度
    - 趋势计算：分析预测结果的趋势方向和强度
    """

    # 默认模型配置
    DEFAULT_CONTEXT_LEN = 256
    DEFAULT_HORIZON_LEN = 32
    DEFAULT_INPUT_PATCH_LEN = 32
    DEFAULT_OUTPUT_PATCH_LEN = 128

    # 最小数据长度要求（TimesFM 要求）
    MIN_DATA_LENGTH = 32

    # 支持的上下文长度选项（TimesFM 预训练配置）
    SUPPORTED_CONTEXT_LENS = [128, 256, 512]

    def __init__(
        self,
        context_len: int = DEFAULT_CONTEXT_LEN,
        horizon_len: int = DEFAULT_HORIZON_LEN,
        backend: str = "cpu",
        model_path: Optional[str] = None,
    ):
        """
        初始化 TimesFM 服务

        Args:
            context_len: 上下文长度（历史数据窗口）
            horizon_len: 预测长度（未来预测步数）
            backend: 推理后端（"cpu" 或 "gpu"）
            model_path: 本地模型路径（可选，默认使用官方预训练模型）
        """
        self.context_len = context_len
        self.horizon_len = horizon_len
        self.backend = backend
        self.model_path = model_path

        # 懒加载相关
        self._model = None
        self._lock = threading.Lock()
        self._loaded = False

        logger.info(
            f"TimesFMService initialized with context_len={context_len}, "
            f"horizon_len={horizon_len}, backend={backend}"
        )

    def _load_model(self) -> None:
        """
        加载 TimesFM 模型（线程安全）

        使用双重检查锁定模式确保只加载一次
        """
        if self._loaded:
            return

        with self._lock:
            # 双重检查
            if self._loaded:
                return

            try:
                import timesfm

                logger.info("Loading TimesFM model...")

                # 使用本地 TimesFM 2.5 包
                self._model = timesfm.TimesFM_2p5_200M_torch(
                    torch_compile=False,  # 禁用 torch compile 加快启动
                )

                # 创建预测配置
                forecast_config = timesfm.ForecastConfig(
                    max_context=self.context_len,
                    max_horizon=self.horizon_len,
                )

                # 编译模型（首次调用时会初始化权重）
                logger.info("Compiling TimesFM model...")
                self._model.compile(forecast_config=forecast_config)
                logger.info("TimesFM model compiled successfully")

                self._loaded = True
                logger.info("TimesFM model loaded successfully")

            except ImportError as e:
                logger.error(f"Failed to import timesfm: {e}")
                raise TimesFMServiceError(
                    "timesfm package not installed. "
                    "Install from: https://github.com/google-research/timesfm"
                )
            except Exception as e:
                logger.error(f"Failed to load TimesFM model: {e}")
                raise TimesFMServiceError(f"Model loading failed: {e}")

    @property
    def model(self):
        """获取模型实例（懒加载）"""
        if not self._loaded:
            self._load_model()
        return self._model

    def _validate_data(self, data: np.ndarray) -> None:
        """
        验证输入数据

        Args:
            data: 输入数据数组

        Raises:
            InsufficientDataError: 数据长度不足
            ValueError: 数据格式无效
        """
        # 先检查类型
        if not isinstance(data, np.ndarray):
            raise ValueError("Input data must be a numpy array")

        # 再检查是否为空
        if data is None or len(data) == 0:
            raise ValueError("Input data cannot be empty")

        # 检查长度
        if len(data) < self.MIN_DATA_LENGTH:
            raise InsufficientDataError(
                f"Data length {len(data)} is less than minimum required {self.MIN_DATA_LENGTH}"
            )

        # 检查 NaN/Inf
        if np.isnan(data).any():
            logger.warning("Input data contains NaN values, interpolation may be needed")

        if np.isinf(data).any():
            raise ValueError("Input data contains infinite values")

    def _adaptive_context_length(self, data_length: int) -> int:
        """
        根据数据长度自适应调整上下文长度

        Args:
            data_length: 输入数据长度

        Returns:
            调整后的上下文长度
        """
        # 如果数据不足默认上下文长度，使用实际长度
        if data_length < self.context_len:
            logger.debug(
                f"Data length {data_length} < context_len {self.context_len}, "
                f"using {data_length}"
            )
            return data_length

        # 如果数据充足，使用默认上下文长度
        return self.context_len

    def _calculate_trend(
        self, predictions: np.ndarray, confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        计算预测趋势

        Args:
            predictions: 预测结果数组
            confidence: 置信度阈值（用于判断趋势强度）

        Returns:
            趋势信息字典，包含：
            - direction: 趋势方向 ("up", "down", "flat")
            - strength: 趋势强度 (0-1)
            - change_pct: 预测期变化百分比
            - start_value: 起始值
            - end_value: 结束值
        """
        if len(predictions) < 2:
            return {
                "direction": "flat",
                "strength": 0.0,
                "change_pct": 0.0,
                "start_value": float(predictions[0]) if len(predictions) > 0 else 0.0,
                "end_value": float(predictions[0]) if len(predictions) > 0 else 0.0,
            }

        start_value = predictions[0]
        end_value = predictions[-1]
        change = end_value - start_value

        # 计算变化百分比
        if abs(start_value) > 1e-6:
            change_pct = (change / abs(start_value)) * 100
        else:
            change_pct = 0.0

        # 判断趋势方向
        if change > confidence * abs(start_value) * 0.01:
            direction = "up"
        elif change < -confidence * abs(start_value) * 0.01:
            direction = "down"
        else:
            direction = "flat"

        # 计算趋势强度（基于线性拟合斜率）
        x = np.arange(len(predictions))
        try:
            # 简单线性回归计算斜率
            slope = np.corrcoef(x, predictions)[0, 1]
            strength = abs(slope) if not np.isnan(slope) else 0.0
        except Exception:
            strength = 0.0

        return {
            "direction": direction,
            "strength": float(strength),
            "change_pct": float(change_pct),
            "start_value": float(start_value),
            "end_value": float(end_value),
        }

    def predict(
        self,
        data: np.ndarray,
        horizon: Optional[int] = None,
        frequency: str = "D",
    ) -> Dict[str, Any]:
        """
        单变量时间序列预测

        Args:
            data: 历史数据（一维数组）
            horizon: 预测长度（None 则使用默认 horizon_len）
            frequency: 数据频率（"D"=日, "H"=小时, "W"=周, "M"=月）

        Returns:
            预测结果字典：
            - predictions: 预测值数组
            - trend: 趋势信息
            - metadata: 元数据（上下文长度、预测长度等）

        Raises:
            InsufficientDataError: 数据不足
            ModelNotLoadedError: 模型未加载
            TimesFMServiceError: 其他预测错误
        """
        # 验证数据
        self._validate_data(data)

        # 确保模型已加载
        if not self._loaded:
            self._load_model()

        # 调整预测长度
        if horizon is None:
            horizon = self.horizon_len

        # 自适应上下文长度
        context_len = self._adaptive_context_length(len(data))
        truncated_data = data[-context_len:]

        try:
            logger.debug(
                f"Running prediction with context_len={context_len}, "
                f"horizon={horizon}, freq={frequency}"
            )

            # TimesFM 2.5 预测
            # forecast 方法签名: (horizon: int, inputs: list[numpy.ndarray])
            # 返回: tuple[predictions, quantiles]
            predictions, quantiles = self._model.forecast(
                horizon=horizon,
                inputs=[truncated_data],
            )

            # predictions 是一个数组，形状为 (horizon,)
            predictions = predictions[0] if len(predictions.shape) > 1 else predictions

            # 计算趋势
            trend = self._calculate_trend(predictions)

            result = {
                "predictions": predictions.tolist(),
                "trend": trend,
                "metadata": {
                    "context_len": context_len,
                    "horizon_len": horizon,
                    "frequency": frequency,
                    "input_length": len(data),
                    "covariates_used": False,
                },
            }

            logger.debug(f"Prediction completed: trend={trend['direction']}")
            return result

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise TimesFMServiceError(f"Prediction failed: {e}")

    def predict_with_covariates(
        self,
        data: np.ndarray,
        covariates: np.ndarray,
        horizon: Optional[int] = None,
        frequency: str = "D",
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        带协变量的时间序列预测

        TimesFM 2.5 通过 forecast_with_covariates() 方法支持协变量，
        协变量可以包含成交量、技术指标等外部特征。

        Args:
            data: 历史数据（一维数组）
            covariates: 协变量矩阵（二维数组，形状为 [n_samples, n_features]）
            horizon: 预测长度（None 则使用默认 horizon_len）
            frequency: 数据频率
            feature_names: 协变量特征名称列表（可选，用于生成字典键）

        Returns:
            预测结果字典：
            - predictions: 预测值数组
            - trend: 趋势信息
            - metadata: 元数据（包含协变量信息）

        Raises:
            InsufficientDataError: 数据不足
            ValueError: 协变量形状不匹配
            TimesFMServiceError: 预测错误
        """
        # 验证数据
        self._validate_data(data)

        # 验证协变量
        if covariates.ndim != 2:
            raise ValueError(
                f"Covariates must be 2D array, got {covariates.ndim}D"
            )

        if len(covariates) != len(data):
            raise ValueError(
                f"Covariates length {len(covariates)} != data length {len(data)}"
            )

        # 确保模型已加载
        if not self._loaded:
            self._load_model()

        # 调整预测长度
        if horizon is None:
            horizon = self.horizon_len

        # 自适应上下文长度
        context_len = self._adaptive_context_length(len(data))
        truncated_data = data[-context_len:]
        truncated_covariates = covariates[-context_len:]

        # 生成特征名称（如果未提供）
        if feature_names is None:
            feature_names = [f"feature_{i}" for i in range(covariates.shape[1])]

        if len(feature_names) != covariates.shape[1]:
            raise ValueError(
                f"Number of feature names {len(feature_names)} != "
                f"number of covariate features {covariates.shape[1]}"
            )

        try:
            logger.debug(
                f"Running prediction with covariates: "
                f"context_len={context_len}, horizon={horizon}, "
                f"n_covariate_features={covariates.shape[1]}"
            )

            # TimesFM 2.5 forecast_with_covariates API
            # 签名: forecast_with_covariates(
            #     inputs: list[Sequence[float]],
            #     dynamic_numerical_covariates: dict[str, Sequence[Sequence[float]]] | None = None,
            #     ...
            # )
            #
            # dynamic_numerical_covariates 格式: {"feature_name": [[values...]]}
            # 注意：values 必须是二维列表（每个时间步一个列表）

            # 将协变量数组转换为 TimesFM 期望的字典格式
            dynamic_numerical_covariates = {}
            for i, feature_name in enumerate(feature_names):
                # 提取第 i 列并转换为嵌套列表格式
                feature_values = truncated_covariates[:, i].tolist()
                # TimesFM 期望每个特征是一个二维列表（外层是时间步，内层是该时间步的值）
                dynamic_numerical_covariates[feature_name] = [feature_values]

            # 调用 forecast_with_covariates
            predictions, quantiles = self._model.forecast_with_covariates(
                inputs=[truncated_data.tolist()],
                dynamic_numerical_covariates=dynamic_numerical_covariates,
            )

            # predictions 是一个数组，形状为 (horizon,)
            predictions = predictions[0] if len(predictions.shape) > 1 else predictions

            # 计算趋势
            trend = self._calculate_trend(predictions)

            result = {
                "predictions": predictions.tolist(),
                "trend": trend,
                "metadata": {
                    "context_len": context_len,
                    "horizon_len": horizon,
                    "frequency": frequency,
                    "input_length": len(data),
                    "covariates_used": True,
                    "n_covariate_features": covariates.shape[1],
                    "feature_names": feature_names,
                },
            }

            logger.debug(
                f"Prediction with covariates completed: "
                f"trend={trend['direction']}, "
                f"used_covariates=True"
            )
            return result

        except Exception as e:
            logger.error(f"Prediction with covariates failed: {e}")
            raise TimesFMServiceError(f"Prediction with covariates failed: {e}")

    def batch_predict(
        self,
        data_list: List[np.ndarray],
        horizon: Optional[int] = None,
        frequency: str = "D",
    ) -> List[Dict[str, Any]]:
        """
        批量时间序列预测

        Args:
            data_list: 历史数据列表（每个元素是一维数组）
            horizon: 预测长度
            frequency: 数据频率

        Returns:
            预测结果列表（每个元素是 predict() 的返回格式）

        Raises:
            InsufficientDataError: 任一数据不足
            TimesFMServiceError: 批量预测错误
        """
        if not data_list:
            return []

        results = []
        errors = []

        for i, data in enumerate(data_list):
            try:
                result = self.predict(data, horizon=horizon, frequency=frequency)
                results.append(result)
            except TimesFMServiceError as e:
                logger.warning(f"Batch prediction failed for item {i}: {e}")
                errors.append((i, str(e)))
                # 添加错误占位符
                results.append({
                    "error": str(e),
                    "predictions": [],
                    "trend": {"direction": "unknown", "strength": 0.0},
                })

        if errors:
            logger.warning(
                f"Batch prediction completed with {len(errors)} errors out of {len(data_list)}"
            )

        return results

    def predict_from_dataframe(
        self,
        df: pd.DataFrame,
        value_column: str,
        date_column: str = "date",
        horizon: Optional[int] = None,
        frequency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从 DataFrame 进行预测

        Args:
            df: 输入数据框
            value_column: 值列名
            date_column: 日期列名
            horizon: 预测长度
            frequency: 数据频率（None 则自动推断）

        Returns:
            预测结果字典

        Raises:
            ValueError: DataFrame 格式无效
            TimesFMServiceError: 预测错误
        """
        # 验证列存在
        if value_column not in df.columns:
            raise ValueError(f"Value column '{value_column}' not found in DataFrame")

        if date_column not in df.columns:
            raise ValueError(f"Date column '{date_column}' not found in DataFrame")

        # 提取数据
        data = df[value_column].values

        # 自动推断频率
        if frequency is None:
            try:
                # 尝试从日期列推断频率
                dates = pd.to_datetime(df[date_column])
                freq = pd.infer_freq(dates)
                if freq:
                    frequency = freq
                else:
                    frequency = "D"  # 默认日频
                logger.debug(f"Inferred frequency: {frequency}")
            except Exception as e:
                logger.warning(f"Failed to infer frequency: {e}, using 'D'")
                frequency = "D"

        return self.predict(data, horizon=horizon, frequency=frequency)

    def is_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._loaded

    def unload(self) -> None:
        """卸载模型（释放内存）"""
        with self._lock:
            if self._loaded:
                self._model = None
                self._loaded = False
                logger.info("TimesFM model unloaded")
