# -*- coding: utf-8 -*-
"""
TimesFM 预测图表数据结构
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ForecastChartConfig:
    """预测图表配置"""

    width: int = 12
    height: int = 6
    dpi: int = 150
    show_confidence: bool = True
    confidence_level: float = 0.8
    show_history_days: int = 90
    format: str = "png"
    style: str = "seaborn-v0_8-whitegrid"


@dataclass
class ForecastChartData:
    """预测图表输出数据"""

    chart_base64: str
    chart_path: Optional[str] = None
    width: int = 0
    height: int = 0
