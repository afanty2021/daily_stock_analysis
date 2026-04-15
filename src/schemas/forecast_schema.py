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
