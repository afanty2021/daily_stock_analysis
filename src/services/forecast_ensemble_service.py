# -*- coding: utf-8 -*-
"""
===================================
预测集成服务
===================================

职责：
1. 管理多个时间序列预测模型
2. 提供统一的预测接口
3. 支持多种集成策略（简单平均、加权平均、中位数）
4. 基于历史准确率动态调整权重
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Type, Optional
import numpy as np

logger = logging.getLogger(__name__)


class ForecastModel(ABC):
    """预测模型基类"""

    @abstractmethod
    def predict(self, data: np.ndarray, horizon: int) -> Dict[str, Any]:
        """
        执行预测

        Args:
            data: 历史数据（一维数组）
            horizon: 预测长度

        Returns:
            预测结果字典，包含：
            - predictions: 预测值数组
            - trend: 趋势信息（可选）
            - metadata: 元数据（可选）
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """模型名称"""
        pass


class ForecastModelRegistry:
    """预测模型注册表"""

    _models: Dict[str, Type[ForecastModel]] = {}

    @classmethod
    def register(cls, name: str, model_cls: Type[ForecastModel]) -> None:
        """
        注册模型

        Args:
            name: 模型名称
            model_cls: 模型类
        """
        cls._models[name] = model_cls
        logger.info(f"Registered forecast model: {name}")

    @classmethod
    def get(cls, name: str) -> Type[ForecastModel]:
        """
        获取模型类

        Args:
            name: 模型名称

        Returns:
            模型类

        Raises:
            KeyError: 模型未注册
        """
        if name not in cls._models:
            raise KeyError(f"Model '{name}' not registered. Available: {list(cls._models.keys())}")
        return cls._models[name]

    @classmethod
    def list_models(cls) -> List[str]:
        """获取所有已注册模型名称"""
        return list(cls._models.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """检查模型是否已注册"""
        return name in cls._models


class TimesFMModel(ForecastModel):
    """TimesFM 模型适配器"""

    def __init__(self, timesfm_service):
        """
        初始化 TimesFM 模型

        Args:
            timesfm_service: TimesFMService 实例
        """
        self._service = timesfm_service

    def predict(self, data: np.ndarray, horizon: int) -> Dict[str, Any]:
        """
        使用 TimesFM 预测

        Args:
            data: 历史数据
            horizon: 预测长度

        Returns:
            预测结果
        """
        return self._service.predict(data, horizon=horizon)

    @property
    def name(self) -> str:
        return "timesfm"


class NaiveSeasonalModel(ForecastModel):
    """
    朴素季节模型（统计基线）

    使用历史季节性模式进行预测：
    - 检测季节性周期（如周、月）
    - 使用最近周期的平均值作为预测
    """

    def __init__(self, seasonality_period: int = 5):
        """
        初始化朴素季节模型

        Args:
            seasonality_period: 季节性周期（默认5，交易日周）
        """
        self._period = seasonality_period

    def predict(self, data: np.ndarray, horizon: int) -> Dict[str, Any]:
        """
        使用季节性模式预测

        Args:
            data: 历史数据
            horizon: 预测长度

        Returns:
            预测结果
        """
        if len(data) < self._period:
            # 数据不足，使用最后值
            predictions = np.full(horizon, data[-1])
        else:
            # 使用最近几个周期的平均值
            last_period = data[-self._period:]
            # 重复季节性模式
            predictions = np.tile(last_period, (horizon // self._period) + 1)[:horizon]

        # 计算简单趋势
        trend = self._calculate_trend(predictions)

        return {
            "predictions": predictions.tolist(),
            "trend": trend,
            "metadata": {
                "model": "naive_seasonal",
                "seasonality_period": self._period,
                "input_length": len(data),
            },
        }

    def _calculate_trend(self, predictions: np.ndarray) -> Dict[str, Any]:
        """计算预测趋势"""
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

        if abs(start_value) > 1e-6:
            change_pct = (change / abs(start_value)) * 100
        else:
            change_pct = 0.0

        if change > 0.01 * abs(start_value):
            direction = "up"
        elif change < -0.01 * abs(start_value):
            direction = "down"
        else:
            direction = "flat"

        # 简单强度计算
        strength = min(abs(change_pct) / 10.0, 1.0)

        return {
            "direction": direction,
            "strength": float(strength),
            "change_pct": float(change_pct),
            "start_value": float(start_value),
            "end_value": float(end_value),
        }

    @property
    def name(self) -> str:
        return "naive_seasonal"


class MovingAverageModel(ForecastModel):
    """
    移动平均模型（统计基线）

    使用简单移动平均进行预测：
    - 计算历史数据的移动平均
    - 预测值为最近移动平均值的延续
    """

    def __init__(self, window: int = 10):
        """
        初始化移动平均模型

        Args:
            window: 移动平均窗口
        """
        self._window = window

    def predict(self, data: np.ndarray, horizon: int) -> Dict[str, Any]:
        """
        使用移动平均预测

        Args:
            data: 历史数据
            horizon: 预测长度

        Returns:
            预测结果
        """
        if len(data) < self._window:
            # 数据不足，使用简单平均
            avg = np.mean(data)
        else:
            # 使用最近窗口的平均值
            avg = np.mean(data[-self._window:])

        # 预测值为平均值的延续
        predictions = np.full(horizon, avg)

        # 计算趋势（通常是平坦的）
        trend = {
            "direction": "flat",
            "strength": 0.0,
            "change_pct": 0.0,
            "start_value": float(avg),
            "end_value": float(avg),
        }

        return {
            "predictions": predictions.tolist(),
            "trend": trend,
            "metadata": {
                "model": "moving_average",
                "window": self._window,
                "input_length": len(data),
            },
        }

    @property
    def name(self) -> str:
        return "moving_average"


class ForecastEnsembleService:
    """
    预测集成服务

    支持多种集成策略：
    - simple: 简单平均
    - weighted: 加权平均（基于历史准确率）
    - median: 中位数集成
    """

    # 支持的集成策略
    STRATEGY_SIMPLE = "simple"
    STRATEGY_WEIGHTED = "weighted"
    STRATEGY_MEDIAN = "median"

    def __init__(
        self,
        models: List[ForecastModel],
        strategy: str = STRATEGY_SIMPLE,
        accuracy_service=None,
    ):
        """
        初始化集成服务

        Args:
            models: 模型列表
            strategy: 集成策略 (simple/weighted/median)
            accuracy_service: 准确率服务（用于加权策略）
        """
        self._models = models
        self._strategy = strategy
        self._accuracy_service = accuracy_service

        logger.info(
            f"ForecastEnsembleService initialized with {len(models)} models, "
            f"strategy={strategy}"
        )

    def predict_ensemble(
        self,
        data: np.ndarray,
        horizon: int,
        stock_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行集成预测

        Args:
            data: 历史数据
            horizon: 预测长度
            stock_code: 股票代码（用于获取历史准确率）

        Returns:
            集成预测结果，包含：
            - predictions: 集成预测值数组
            - trend: 趋势信息
            - metadata: 元数据（包含各模型预测）
        """
        if not self._models:
            raise ValueError("No models available for ensemble")

        # 收集各模型预测
        model_predictions = []
        model_names = []
        errors = []

        for model in self._models:
            try:
                result = model.predict(data, horizon)
                if "predictions" in result and result["predictions"]:
                    model_predictions.append(np.array(result["predictions"]))
                    model_names.append(model.name)
                else:
                    logger.warning(f"Model {model.name} returned empty predictions")
                    errors.append(f"{model.name}: empty predictions")
            except Exception as e:
                logger.warning(f"Model {model.name} prediction failed: {e}")
                errors.append(f"{model.name}: {str(e)}")

        if not model_predictions:
            raise ValueError(f"All models failed: {errors}")

        # 合并预测
        combined = self._combine_predictions(
            model_predictions,
            model_names,
            stock_code=stock_code,
        )

        # 计算集成趋势
        trend = self._calculate_ensemble_trend(combined["predictions"])

        return {
            "predictions": combined["predictions"].tolist(),
            "trend": trend,
            "metadata": {
                "ensemble_strategy": self._strategy,
                "n_models": len(model_predictions),
                "model_names": model_names,
                "individual_predictions": [
                    pred.tolist() for pred in model_predictions
                ],
                "weights": combined.get("weights", None),
                "errors": errors,
            },
        }

    def _combine_predictions(
        self,
        predictions: List[np.ndarray],
        model_names: List[str],
        stock_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        合并多个模型预测

        Args:
            predictions: 预测值列表
            model_names: 模型名称列表
            stock_code: 股票代码（用于获取权重）

        Returns:
            合并结果，包含 predictions 和 weights
        """
        if self._strategy == self.STRATEGY_SIMPLE:
            # 简单平均
            combined = np.mean(predictions, axis=0)
            return {"predictions": combined, "weights": None}

        elif self._strategy == self.STRATEGY_MEDIAN:
            # 中位数
            combined = np.median(predictions, axis=0)
            return {"predictions": combined, "weights": None}

        elif self._strategy == self.STRATEGY_WEIGHTED:
            # 加权平均
            weights = self._calculate_weights(model_names, stock_code)
            weighted_predictions = [
                pred * weight for pred, weight in zip(predictions, weights)
            ]
            combined = np.sum(weighted_predictions, axis=0)
            return {"predictions": combined, "weights": weights.tolist()}

        else:
            logger.warning(f"Unknown strategy '{self._strategy}', falling back to simple")
            combined = np.mean(predictions, axis=0)
            return {"predictions": combined, "weights": None}

    def _calculate_weights(
        self,
        model_names: List[str],
        stock_code: Optional[str] = None,
    ) -> np.ndarray:
        """
        基于历史准确率计算权重

        Args:
            model_names: 模型名称列表
            stock_code: 股票代码

        Returns:
            权重数组（归一化，和为1）
        """
        n_models = len(model_names)

        # 如果没有准确率服务，使用均等权重
        if self._accuracy_service is None:
            logger.debug("No accuracy service, using equal weights")
            return np.ones(n_models) / n_models

        try:
            # 获取历史准确率（这里简化处理，实际应该从数据库查询）
            # 暂时使用均等权重，后续可以根据历史 MAPE 调整
            logger.debug(
                f"Using equal weights for {model_names} "
                f"(accuracy-based weights not yet implemented)"
            )
            return np.ones(n_models) / n_models

        except Exception as e:
            logger.warning(f"Failed to calculate weights: {e}, using equal weights")
            return np.ones(n_models) / n_models

    def _calculate_ensemble_trend(self, predictions: np.ndarray) -> Dict[str, Any]:
        """
        计算集成预测趋势

        Args:
            predictions: 预测值数组

        Returns:
            趋势信息
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

        if abs(start_value) > 1e-6:
            change_pct = (change / abs(start_value)) * 100
        else:
            change_pct = 0.0

        # 判断趋势方向
        if change > 0.01 * abs(start_value):
            direction = "up"
        elif change < -0.01 * abs(start_value):
            direction = "down"
        else:
            direction = "flat"

        # 计算趋势强度
        x = np.arange(len(predictions))
        try:
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

    def set_strategy(self, strategy: str) -> None:
        """
        设置集成策略

        Args:
            strategy: 新策略 (simple/weighted/median)
        """
        valid_strategies = [
            self.STRATEGY_SIMPLE,
            self.STRATEGY_WEIGHTED,
            self.STRATEGY_MEDIAN,
        ]
        if strategy not in valid_strategies:
            raise ValueError(
                f"Invalid strategy '{strategy}'. Must be one of {valid_strategies}"
            )
        self._strategy = strategy
        logger.info(f"Ensemble strategy changed to: {strategy}")

    @property
    def strategy(self) -> str:
        """当前集成策略"""
        return self._strategy

    @property
    def n_models(self) -> int:
        """模型数量"""
        return len(self._models)


# 注册内置模型
ForecastModelRegistry.register("timesfm", TimesFMModel)
ForecastModelRegistry.register("naive_seasonal", NaiveSeasonalModel)
ForecastModelRegistry.register("moving_average", MovingAverageModel)
