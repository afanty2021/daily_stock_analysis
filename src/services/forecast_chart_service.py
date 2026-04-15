# -*- coding: utf-8 -*-
"""
===================================
TimesFM 预测图表生成服务
===================================

职责：
1. 根据历史价格和预测数据生成 matplotlib 图表
2. 输出 base64 编码的 PNG 图片
3. 支持置信区间显示
"""

import base64
import io
import logging
from datetime import datetime, timedelta
from typing import List, Optional

import numpy as np

from src.schemas.forecast_chart_schema import ForecastChartConfig, ForecastChartData

logger = logging.getLogger(__name__)

# 交易日近似：一年约 252 个交易日，一个月约 21 个交易日
_TRADING_DAYS_PER_WEEK = 5


def _generate_forecast_dates(
    history_dates: List[str],
    horizon: int,
) -> List[str]:
    """
    基于历史日期列表生成预测期间日期字符串列表。

    简单地从历史最后一个日期开始，每个预测步加 1 天并跳过周末。

    Args:
        history_dates: 历史日期字符串列表（YYYY-MM-DD 格式）
        horizon: 预测步数

    Returns:
        预测日期字符串列表
    """
    if not history_dates:
        today = datetime.now()
    else:
        try:
            today = datetime.strptime(history_dates[-1], "%Y-%m-%d")
        except (ValueError, TypeError):
            today = datetime.now()

    dates = []
    current = today
    for _ in range(horizon):
        current = current + timedelta(days=1)
        # 跳过周末
        while current.weekday() >= 5:
            current = current + timedelta(days=1)
        dates.append(current.strftime("%Y-%m-%d"))
    return dates


def _plot_history(ax, prices: np.ndarray, dates: List[str]):
    """
    绘制历史价格折线

    Args:
        ax: matplotlib Axes 对象
        prices: 历史收盘价数组
        dates: 历史日期列表
    """
    x = list(range(len(prices)))
    ax.plot(x, prices, color="#2196F3", linewidth=1.5, label="历史价格")

    # 设置 x 轴日期标签（只显示部分避免拥挤）
    tick_step = max(1, len(dates) // 8)
    tick_positions = list(range(0, len(dates), tick_step))
    tick_labels = [dates[i] if i < len(dates) else "" for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=30, ha="right", fontsize=8)


def _plot_forecast(ax, forecast: np.ndarray, offset: int):
    """
    绘制预测折线（虚线）

    Args:
        ax: matplotlib Axes 对象
        forecast: 预测值数组
        offset: x 轴起始偏移（历史数据长度）
    """
    x = list(range(offset, offset + len(forecast)))
    ax.plot(x, forecast, color="#F44336", linewidth=1.5, linestyle="--", label="预测价格")


def _plot_confidence_band(
    ax,
    quantile_forecast: np.ndarray,
    offset: int,
    confidence_level: float = 0.8,
):
    """
    绘制置信区间填充区域

    Args:
        ax: matplotlib Axes 对象
        quantile_forecast: 分位数预测 (horizon, 10)，列为 10%-90%
        offset: x 轴起始偏移
        confidence_level: 置信水平
    """
    horizon = quantile_forecast.shape[0]

    if confidence_level == 0.8:
        lower = quantile_forecast[:, 0]  # 10%
        upper = quantile_forecast[:, 9]  # 90%
    elif confidence_level == 0.6:
        lower = quantile_forecast[:, 1]  # 20%
        upper = quantile_forecast[:, 8]  # 80%
    else:
        lower = quantile_forecast[:, 0]
        upper = quantile_forecast[:, 9]

    x = list(range(offset, offset + horizon))
    ax.fill_between(
        x,
        lower,
        upper,
        alpha=0.2,
        color="#F44336",
        label=f"{int(confidence_level * 100)}% 置信区间",
    )


def _chart_to_base64(fig) -> str:
    """
    将 matplotlib Figure 转为 base64 编码的 PNG 字符串

    Args:
        fig: matplotlib Figure 对象

    Returns:
        base64 编码的 PNG 字符串
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=fig.dpi, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    buf.close()
    return encoded


def generate_forecast_chart(
    prices: np.ndarray,
    dates: List[str],
    point_forecast: np.ndarray,
    quantile_forecast: np.ndarray,
    config: Optional[ForecastChartConfig] = None,
) -> ForecastChartData:
    """
    生成预测图表

    Args:
        prices: 历史收盘价数组 (1D)
        dates: 历史日期字符串列表
        point_forecast: 预测值数组 (1D)
        quantile_forecast: 分位数预测 (horizon, 10)
        config: 图表配置（可选）

    Returns:
        ForecastChartData 包含 base64 编码的 PNG 图片
    """
    import matplotlib
    matplotlib.use("Agg")  # 非交互式后端
    import matplotlib.pyplot as plt

    if config is None:
        config = ForecastChartConfig()

    # 尝试设置样式，如果不可用则回退
    try:
        plt.style.use(config.style)
    except OSError:
        try:
            plt.style.use("seaborn-whitegrid")
        except OSError:
            pass  # 使用默认样式

    # 限制历史天数
    if config.show_history_days > 0 and len(prices) > config.show_history_days:
        prices = prices[-config.show_history_days:]
        dates = dates[-config.show_history_days:]

    # 生成预测日期
    forecast_dates = _generate_forecast_dates(dates, len(point_forecast))

    # 创建图表
    fig, ax = plt.subplots(figsize=(config.width, config.height), dpi=config.dpi)

    # 1. 绘制历史价格
    _plot_history(ax, prices, dates)

    offset = len(prices)

    # 2. 绘制 "今天" 分割线
    ax.axvline(
        x=offset - 0.5,
        color="#4CAF50",
        linewidth=1.2,
        linestyle="-",
        alpha=0.8,
        label="今天",
    )

    # 3. 绘制预测价格
    _plot_forecast(ax, point_forecast, offset)

    # 4. 绘制置信区间
    if config.show_confidence and quantile_forecast is not None:
        _plot_confidence_band(ax, quantile_forecast, offset, config.confidence_level)

    # 5. 添加预测区间 x 轴标签
    forecast_tick_step = max(1, len(forecast_dates) // 6)
    forecast_tick_positions = list(range(offset, offset + len(forecast_dates), forecast_tick_step))
    forecast_tick_labels = [
        forecast_dates[i - offset] if 0 <= i - offset < len(forecast_dates) else ""
        for i in forecast_tick_positions
    ]

    # 合并 x 轴刻度
    history_tick_step = max(1, len(dates) // 8)
    history_tick_positions = list(range(0, len(dates), history_tick_step))
    all_tick_positions = history_tick_positions + forecast_tick_positions
    all_tick_labels = (
        [dates[i] if i < len(dates) else "" for i in history_tick_positions]
        + forecast_tick_labels
    )
    ax.set_xticks(all_tick_positions)
    ax.set_xticklabels(all_tick_labels, rotation=30, ha="right", fontsize=8)

    # 6. 图表装饰
    ax.set_title("AI 价格预测", fontsize=14, fontweight="bold")
    ax.set_xlabel("日期", fontsize=10)
    ax.set_ylabel("价格", fontsize=10)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    # 7. 转为 base64
    chart_base64 = _chart_to_base64(fig)
    result = ForecastChartData(
        chart_base64=chart_base64,
        width=config.width,
        height=config.height,
    )

    plt.close(fig)

    return result
