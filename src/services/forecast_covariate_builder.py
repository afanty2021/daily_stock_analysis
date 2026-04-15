# -*- coding: utf-8 -*-
"""
===================================
协变量构建器 (Covariate Builder)
===================================

职责：
1. 构建用于 TimesFM 预测的协变量矩阵
2. 支持成交量、技术指标等多种协变量
3. 验证和标准化协变量数据
4. 提供可复用的特征构建接口
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)


class CovariateFeature(Enum):
    """支持的协变量特征类型"""
    VOLUME_CHANGE = "volume_change"  # 成交量变化率
    MA_DEVIATION = "ma_deviation"    # 移动平均线偏离度
    RSI = "rsi"                      # 相对强弱指标
    BOLLINGER_POSITION = "bollinger_position"  # 布林带位置


class CovariateBuilderError(Exception):
    """协变量构建器异常基类"""
    pass


class InsufficientDataError(CovariateBuilderError):
    """数据不足异常"""
    pass


class ValidationError(CovariateBuilderError):
    """数据验证异常"""
    pass


class ForecastCovariateBuilder:
    """
    预测协变量构建器

    功能：
    - 构建多维度协变量矩阵
    - 支持多种技术指标特征
    - 自动验证和标准化数据
    - 可扩展的特征架构

    协变量说明：
    - volume_change: 成交量变化率（当前成交量 vs 平均成交量）
    - ma_deviation: 价格相对于 MA5/MA10/MA20 的偏离度
    - rsi: 相对强弱指标（14日）
    - bollinger_position: 价格在布林带中的位置（0-1）
    """

    # 默认配置
    DEFAULT_RSI_PERIOD = 14
    DEFAULT_MA_PERIODS = [5, 10, 20]
    DEFAULT_BOLLINGER_PERIOD = 20
    DEFAULT_BOLLINGER_STD = 2

    # 最小数据长度要求
    MIN_DATA_LENGTH = 32

    def __init__(
        self,
        enabled_features: Optional[List[str]] = None,
        rsi_period: int = DEFAULT_RSI_PERIOD,
        ma_periods: Optional[List[int]] = None,
        bollinger_period: int = DEFAULT_BOLLINGER_PERIOD,
        bollinger_std: float = DEFAULT_BOLLINGER_STD,
    ):
        """
        初始化协变量构建器

        Args:
            enabled_features: 启用的特征列表（None 表示使用默认）
            rsi_period: RSI 计算周期
            ma_periods: MA 周期列表
            bollinger_period: 布林带周期
            bollinger_std: 布林带标准差倍数
        """
        # 默认启用所有特征
        if enabled_features is None:
            self.enabled_features = [
                CovariateFeature.VOLUME_CHANGE.value,
                CovariateFeature.MA_DEVIATION.value,
                CovariateFeature.RSI.value,
                CovariateFeature.BOLLINGER_POSITION.value,
            ]
        else:
            self.enabled_features = enabled_features

        self.rsi_period = rsi_period
        self.ma_periods = ma_periods or self.DEFAULT_MA_PERIODS
        self.bollinger_period = bollinger_period
        self.bollinger_std = bollinger_std

        logger.debug(
            f"ForecastCovariateBuilder initialized with features: {self.enabled_features}"
        )

    def build_covariates(
        self,
        prices: np.ndarray,
        volumes: Optional[np.ndarray] = None,
        dates: Optional[List[str]] = None,
    ) -> np.ndarray:
        """
        构建协变量矩阵

        Args:
            prices: 价格序列（必需）
            volumes: 成交量序列（可选，volume_change 特征需要）
            dates: 日期列表（可选，用于日志）

        Returns:
            协变量矩阵，形状为 (n_samples, n_features)

        Raises:
            InsufficientDataError: 数据长度不足
            ValidationError: 数据验证失败
        """
        # 验证输入数据
        self._validate_input(prices, volumes)

        n_samples = len(prices)
        feature_list = []

        # 构建每个启用的特征
        for feature_name in self.enabled_features:
            try:
                if feature_name == CovariateFeature.VOLUME_CHANGE.value:
                    feature = self._build_volume_change(prices, volumes)
                elif feature_name == CovariateFeature.MA_DEVIATION.value:
                    feature = self._build_ma_deviation(prices)
                elif feature_name == CovariateFeature.RSI.value:
                    feature = self._build_rsi(prices)
                elif feature_name == CovariateFeature.BOLLINGER_POSITION.value:
                    feature = self._build_bollinger_position(prices)
                else:
                    logger.warning(f"Unknown feature: {feature_name}, skipping")
                    continue

                feature_list.append(feature)

            except Exception as e:
                logger.warning(f"Failed to build feature {feature_name}: {e}, skipping")
                continue

        if not feature_list:
            logger.warning("No valid features built, returning zero matrix")
            return np.zeros((n_samples, 1))

        # 合并所有特征
        covariates = np.column_stack(feature_list)

        logger.debug(
            f"Built covariate matrix: shape={covariates.shape}, "
            f"features={len(feature_list)}"
        )

        return covariates

    def _validate_input(
        self,
        prices: np.ndarray,
        volumes: Optional[np.ndarray] = None,
    ) -> None:
        """
        验证输入数据

        Args:
            prices: 价格序列
            volumes: 成交量序列

        Raises:
            InsufficientDataError: 数据长度不足
            ValidationError: 数据格式无效
        """
        # 检查价格数据
        if not isinstance(prices, np.ndarray):
            raise ValidationError("Prices must be a numpy array")

        if len(prices) < self.MIN_DATA_LENGTH:
            raise InsufficientDataError(
                f"Price data length {len(prices)} is less than "
                f"minimum required {self.MIN_DATA_LENGTH}"
            )

        # 检查成交量数据（如果提供）
        if volumes is not None:
            if not isinstance(volumes, np.ndarray):
                raise ValidationError("Volumes must be a numpy array")

            if len(volumes) != len(prices):
                raise ValidationError(
                    f"Volumes length {len(volumes)} != prices length {len(prices)}"
                )

        # 检查 NaN/Inf
        if np.isnan(prices).any():
            logger.warning("Price data contains NaN values")

        if np.isinf(prices).any():
            raise ValidationError("Price data contains infinite values")

    def _build_volume_change(
        self,
        prices: np.ndarray,
        volumes: Optional[np.ndarray],
    ) -> np.ndarray:
        """
        构建成交量变化率特征

        计算逻辑：
        - 计算成交量相对于 MA20 的比率
        - 标准化到 [-1, 1] 区间

        Args:
            prices: 价格序列
            volumes: 成交量序列

        Returns:
            成交量变化率特征数组
        """
        if volumes is None:
            # 如果没有成交量数据，返回零特征
            logger.warning("Volume data not provided, returning zero volume_change feature")
            return np.zeros(len(prices))

        # 计算成交量 MA20
        ma_volume = self._compute_ma(volumes, period=20)

        # 计算变化率（避免除零）
        with np.errstate(divide='ignore', invalid='ignore'):
            volume_change = (volumes - ma_volume) / (ma_volume + 1e-8)

        # 标准化到 [-1, 1]
        volume_change = np.clip(volume_change, -2, 2)
        volume_change = np.tanh(volume_change)

        return volume_change

    def _build_ma_deviation(self, prices: np.ndarray) -> np.ndarray:
        """
        构建移动平均线偏离度特征

        计算逻辑：
        - 计算价格相对于 MA5/MA10/MA20 的偏离度
        - 返回平均偏离度

        Args:
            prices: 价格序列

        Returns:
            MA 偏离度特征数组
        """
        deviations = []

        for period in self.ma_periods:
            ma = self._compute_ma(prices, period=period)

            # 计算偏离度（百分比）
            with np.errstate(divide='ignore', invalid='ignore'):
                deviation = (prices - ma) / (ma + 1e-8)

            deviations.append(deviation)

        # 平均偏离度
        avg_deviation = np.mean(deviations, axis=0)

        # 标准化到 [-1, 1]
        avg_deviation = np.clip(avg_deviation, -0.5, 0.5)
        avg_deviation = np.tanh(avg_deviation * 2)

        return avg_deviation

    def _build_rsi(self, prices: np.ndarray) -> np.ndarray:
        """
        构建 RSI 指标特征

        计算逻辑：
        - 使用 14 日 RSI
        - 标准化到 [0, 1] 区间

        Args:
            prices: 价格序列

        Returns:
            RSI 特征数组
        """
        # 计算价格变化
        price_diff = np.diff(prices, prepend=prices[0])

        # 分离涨跌
        gains = np.where(price_diff > 0, price_diff, 0)
        losses = np.where(price_diff < 0, -price_diff, 0)

        # 计算平均涨跌（使用指数移动平均）
        alpha = 1.0 / self.rsi_period
        avg_gains = self._compute_ema(gains, alpha=alpha)
        avg_losses = self._compute_ema(losses, alpha=alpha)

        # 计算 RSI
        with np.errstate(divide='ignore', invalid='ignore'):
            rs = avg_gains / (avg_losses + 1e-8)
            rsi = 100 - (100 / (1 + rs))

        # 标准化到 [0, 1]
        rsi_normalized = rsi / 100.0

        # 处理 NaN（前几个点可能为 NaN）
        rsi_normalized = np.nan_to_num(rsi_normalized, nan=0.5)

        return rsi_normalized

    def _build_bollinger_position(self, prices: np.ndarray) -> np.ndarray:
        """
        构建布林带位置特征

        计算逻辑：
        - 计算布林带上下轨
        - 计算价格在布林带中的相对位置（0-1）

        Args:
            prices: 价格序列

        Returns:
            布林带位置特征数组
        """
        # 计算布林带中轨（MA）
        middle_band = self._compute_ma(prices, period=self.bollinger_period)

        # 计算标准差
        rolling_std = self._compute_rolling_std(prices, period=self.bollinger_period)

        # 计算上下轨
        upper_band = middle_band + self.bollinger_std * rolling_std
        lower_band = middle_band - self.bollinger_std * rolling_std

        # 计算位置（0-1）
        with np.errstate(divide='ignore', invalid='ignore'):
            position = (prices - lower_band) / (upper_band - lower_band + 1e-8)

        # 处理 NaN
        position = np.nan_to_num(position, nan=0.5)

        return position

    def _compute_ma(self, data: np.ndarray, period: int) -> np.ndarray:
        """
        计算简单移动平均

        Args:
            data: 输入数据
            period: 周期

        Returns:
            移动平均数组
        """
        ma = np.zeros_like(data)

        for i in range(period - 1, len(data)):
            ma[i] = np.mean(data[i - period + 1 : i + 1])

        # 前面的点使用前向填充
        ma[: period - 1] = ma[period - 1] if period <= len(data) else 0

        return ma

    def _compute_ema(self, data: np.ndarray, alpha: float) -> np.ndarray:
        """
        计算指数移动平均

        Args:
            data: 输入数据
            alpha: 平滑系数

        Returns:
            指数移动平均数组
        """
        ema = np.zeros_like(data)
        ema[0] = data[0]

        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]

        return ema

    def get_feature_names(self) -> List[str]:
        """
        获取当前启用的特征名称列表

        Returns:
            特征名称列表，顺序与 build_covariates() 返回的矩阵列顺序一致
        """
        feature_names = []
        for feature_name in self.enabled_features:
            if feature_name in [
                CovariateFeature.VOLUME_CHANGE.value,
                CovariateFeature.MA_DEVIATION.value,
                CovariateFeature.RSI.value,
                CovariateFeature.BOLLINGER_POSITION.value,
            ]:
                # 所有特征每个只生成一列
                # 注意：MA_DEVIATION 虽然使用多个周期计算，但最终返回平均值作为单一列
                feature_names.append(feature_name)
            else:
                logger.warning(f"Unknown feature: {feature_name}, skipping")

        return feature_names

    def _compute_rolling_std(self, data: np.ndarray, period: int) -> np.ndarray:
        """
        计算滚动标准差

        Args:
            data: 输入数据
            period: 周期

        Returns:
            滚动标准差数组
        """
        rolling_std = np.zeros_like(data)

        for i in range(period - 1, len(data)):
            rolling_std[i] = np.std(data[i - period + 1 : i + 1])

        # 前面的点使用前向填充
        rolling_std[: period - 1] = (
            rolling_std[period - 1] if period <= len(data) else 0
        )

        return rolling_std

    def validate_covariates(self, covariates: np.ndarray) -> Dict[str, Any]:
        """
        验证协变量数据质量

        Args:
            covariates: 协变量矩阵

        Returns:
            验证结果字典，包含：
            - is_valid: 是否有效
            - n_samples: 样本数
            - n_features: 特征数
            - nan_count: NaN 数量
            - inf_count: Inf 数量
            - warnings: 警告列表
        """
        warnings = []

        # 检查形状
        if covariates.ndim != 2:
            warnings.append(f"Covariates should be 2D, got {covariates.ndim}D")

        # 检查 NaN/Inf
        nan_count = np.isnan(covariates).sum()
        inf_count = np.isinf(covariates).sum()

        if nan_count > 0:
            warnings.append(f"Found {nan_count} NaN values in covariates")

        if inf_count > 0:
            warnings.append(f"Found {inf_count} Inf values in covariates")

        # 检查数值范围
        if covariates.size > 0:
            min_val = np.nanmin(covariates)
            max_val = np.nanmax(covariates)

            if abs(min_val) > 10 or abs(max_val) > 10:
                warnings.append(
                    f"Covariate values out of reasonable range: [{min_val:.2f}, {max_val:.2f}]"
                )

        is_valid = len(warnings) == 0

        return {
            "is_valid": is_valid,
            "n_samples": covariates.shape[0] if covariates.ndim >= 1 else 0,
            "n_features": covariates.shape[1] if covariates.ndim == 2 else 0,
            "nan_count": int(nan_count),
            "inf_count": int(inf_count),
            "warnings": warnings,
        }

    def normalize_covariates(
        self,
        covariates: np.ndarray,
        method: str = "standard",
    ) -> np.ndarray:
        """
        标准化协变量

        Args:
            covariates: 协变量矩阵
            method: 标准化方法（"standard", "minmax", "robust"）

        Returns:
            标准化后的协变量矩阵
        """
        if method == "standard":
            # Z-score 标准化
            mean = np.nanmean(covariates, axis=0)
            std = np.nanstd(covariates, axis=0)
            normalized = (covariates - mean) / (std + 1e-8)

        elif method == "minmax":
            # Min-Max 标准化到 [0, 1]
            min_val = np.nanmin(covariates, axis=0)
            max_val = np.nanmax(covariates, axis=0)
            normalized = (covariates - min_val) / (max_val - min_val + 1e-8)

        elif method == "robust":
            # 鲁棒标准化（使用中位数和 MAD）
            median = np.nanmedian(covariates, axis=0)
            mad = np.nanmedian(np.abs(covariates - median), axis=0)
            normalized = (covariates - median) / (mad + 1e-8)

        else:
            raise ValueError(f"Unknown normalization method: {method}")

        # 处理 NaN/Inf
        normalized = np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=-1.0)

        return normalized
