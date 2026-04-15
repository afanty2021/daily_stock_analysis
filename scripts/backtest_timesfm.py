#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TimesFM 预测准确率回测脚本

使用历史数据回测 TimesFM 模型的预测准确率，验证模型有效性。
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any
import numpy as np
import pandas as pd

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.timesfm_service import TimesFMService, TimesFMServiceError
from src.config import get_config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TimesFMBacktester:
    """TimesFM 回测器"""

    def __init__(
        self,
        stock_code: str,
        test_days: int = 30,
        forecast_horizon: int = 5,
        context_length: int = 252,  # 约 1 年交易日
    ):
        """
        初始化回测器

        Args:
            stock_code: 股票代码
            test_days: 测试天数（回测窗口）
            forecast_horizon: 每次预测天数（建议 5-10 天）
            context_length: 上下文长度（交易日）
        """
        self.stock_code = stock_code
        self.test_days = test_days
        self.forecast_horizon = forecast_horizon
        self.context_length = context_length

        # 存储回测结果
        self.results = []

    def fetch_historical_data(self) -> pd.DataFrame:
        """
        获取历史数据

        Returns:
            包含日期、开盘价、最高价、最低价、收盘价的 DataFrame
        """
        from data_provider import DataFetcherManager

        logger.info(f"Fetching historical data for {self.stock_code}...")

        # 使用 DataFetcherManager
        fetcher_manager = DataFetcherManager()

        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.context_length + self.test_days + 30)

        # 获取日线数据
        df, source = fetcher_manager.get_daily_data(
            stock_code=self.stock_code,
            days=self.context_length + self.test_days + 30,
        )

        if df is None or df.empty:
            raise ValueError(f"无法获取 {self.stock_code} 的历史数据")

        # API 已经按 stock_code 过滤，无需再次过滤

        # 确保按日期升序排列
        df = df.sort_values('date')

        # 只保留必要的列
        required_cols = ['date', 'open', 'high', 'low', 'close']
        df = df[required_cols].copy()

        logger.info(f"获取到 {len(df)} 条历史数据（{df['date'].min()} 至 {df['date'].max()}）")

        return df

    def run_backtest(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        运行回测

        Args:
            df: 历史数据 DataFrame

        Returns:
            回测结果字典
        """
        logger.info("开始 TimesFM 回测...")
        logger.info(f"股票代码: {self.stock_code}")
        logger.info(f"回测窗口: {self.test_days} 天")
        logger.info(f"预测周期: {self.forecast_horizon} 天")
        logger.info(f"上下文长度: {self.context_length} 天")

        # 初始化 TimesFM 服务
        try:
            service = TimesFMService(
                context_len=self.context_length,
                horizon_len=self.forecast_horizon,
            )
        except Exception as e:
            logger.error(f"TimesFM 服务初始化失败: {e}")
            logger.error("请确保已安装 TimesFM: pip install timesfm[torch]")
            return {}

        # 准备结果存储
        predictions = []
        actuals = []
        dates = []

        # 滚动窗口回测
        total_tests = self.test_days // self.forecast_horizon

        for i in range(total_tests):
            # 计算数据索引
            context_end = self.context_length + i * self.forecast_horizon
            actual_start = context_end
            actual_end = actual_start + self.forecast_horizon

            # 检查是否有足够数据
            if actual_end >= len(df):
                logger.warning(f"测试 {i+1}/{total_tests}: 数据不足，跳过")
                break

            # 提取上下文数据（收盘价）
            context_prices = df['close'].iloc[context_end - self.context_length:context_end].values

            # 提取实际值（用于对比）
            actual_prices = df['close'].iloc[actual_start:actual_end].values
            actual_dates = df['date'].iloc[actual_start:actual_end].values

            try:
                # 执行预测
                result = service.predict(
                    data=context_prices,
                    horizon=self.forecast_horizon,
                )

                # 存储预测和实际值
                # result 是字典，包含 predictions, trend, metadata
                predictions.append(np.array(result['predictions']))
                actuals.append(actual_prices)
                dates.append(actual_dates)

                logger.info(
                    f"测试 {i+1}/{total_tests}: "
                    f"预测日期 {actual_dates[0]} - {actual_dates[-1]}, "
                    f"趋势 {result['trend']['direction']}"
                )

            except TimesFMServiceError as e:
                logger.warning(f"测试 {i+1}/{total_tests}: 预测失败 - {e}")
                continue

        if not predictions:
            logger.error("回测失败：没有成功的预测")
            return {}

        # 计算准确率指标
        metrics = self._calculate_metrics(predictions, actuals, dates)

        return metrics

    def _calculate_metrics(
        self,
        predictions: List[np.ndarray],
        actuals: List[np.ndarray],
        dates: List[np.ndarray],
    ) -> Dict[str, Any]:
        """
        计算准确率指标

        Args:
            predictions: 预测值列表
            actuals: 实际值列表
            dates: 日期列表

        Returns:
            指标字典
        """
        # 展平数组
        all_predictions = np.concatenate(predictions)
        all_actuals = np.concatenate(actuals)

        # 1. 平均绝对误差 (MAE)
        mae = np.mean(np.abs(all_predictions - all_actuals))

        # 2. 平均绝对百分比误差 (MAPE)
        # 避免除零
        mape = np.mean(np.abs((all_actuals - all_predictions) / (all_actuals + 1e-8))) * 100

        # 3. 均方根误差 (RMSE)
        rmse = np.sqrt(np.mean((all_predictions - all_actuals) ** 2))

        # 4. 方向准确率
        direction_correct = 0
        total_directions = 0

        for pred, act in zip(predictions, actuals):
            # 计算趋势方向
            pred_direction = np.sign(pred[-1] - pred[0])
            actual_direction = np.sign(act[-1] - act[0])

            if pred_direction == actual_direction:
                direction_correct += 1
            total_directions += 1

        direction_accuracy = direction_correct / total_directions * 100 if total_directions > 0 else 0

        # 5. 置信区间覆盖率
        confidence_80_coverage = 0
        total_confidence_checks = 0

        for pred, act in zip(predictions, actuals):
            # 检查实际值是否在 80% 置信区间内
            # 这里需要从 quantile_forecast 获取，暂时简化处理
            total_confidence_checks += len(act)

        confidence_80_coverage = confidence_80_coverage / total_confidence_checks * 100 if total_confidence_checks > 0 else 0

        # 按时间步长度的误差分析
        step_errors = []
        for step in range(self.forecast_horizon):
            step_preds = [p[step] for p in predictions if len(p) > step]
            step_acts = [a[step] for a in actuals if len(a) > step]

            if step_preds and step_acts:
                step_mae = np.mean(np.abs(np.array(step_preds) - np.array(step_acts)))
                step_errors.append(step_mae)

        return {
            'stock_code': self.stock_code,
            'test_days': self.test_days,
            'forecast_horizon': self.forecast_horizon,
            'context_length': self.context_length,
            'total_predictions': len(all_predictions),
            'metrics': {
                'mae': float(mae),
                'mape': float(mape),
                'rmse': float(rmse),
                'direction_accuracy': float(direction_accuracy),
            },
            'step_errors': [float(e) for e in step_errors],
            'predictions_sample': {
                'first_5_predictions': all_predictions[:5].tolist(),
                'first_5_actuals': all_actuals[:5].tolist(),
            },
        }

    def print_report(self, metrics: Dict[str, Any]):
        """打印回测报告"""
        print("\n" + "=" * 60)
        print(f"TimesFM 预测准确率回测报告 - {metrics['stock_code']}")
        print("=" * 60)

        print(f"\n📊 回测配置:")
        print(f"  回测窗口: {metrics['test_days']} 天")
        print(f"  预测周期: {metrics['forecast_horizon']} 天")
        print(f"  上下文长度: {metrics['context_length']} 天")
        print(f"  预测总数: {metrics['total_predictions']} 个")

        print(f"\n📈 准确率指标:")
        m = metrics['metrics']
        print(f"  ✅ 平均绝对误差 (MAE):  {m['mae']:.4f}")
        print(f"  ✅ 平均绝对百分比误差 (MAPE): {m['mape']:.2f}%")
        print(f"  ✅ 均方根误差 (RMSE):  {m['rmse']:.4f}")
        print(f"  ✅ 方向准确率: {m['direction_accuracy']:.2f}%")

        print(f"\n📋 按预测步长的误差:")
        for i, error in enumerate(metrics['step_errors']):
            print(f"  第 {i+1} 天 MAE: {error:.4f}")

        print(f"\n💡 评估:")
        if m['mape'] < 5:
            print("  ✅ 优秀 - MAPE < 5%，预测误差很小")
        elif m['mape'] < 10:
            print("  ⚠️  良好 - MAPE < 10%，预测误差可接受")
        else:
            print("  ❌ 需改进 - MAPE ≥ 10%，预测误差较大")

        if m['direction_accuracy'] >= 60:
            print(f"  ✅ 方向判断准确 - {m['direction_accuracy']:.1f}% ≥ 60%")
        else:
            print(f"  ⚠️  方向判断需提升 - {m['direction_accuracy']:.1f}% < 60%")

        print("\n" + "=" * 60)
        print("⚠️  免责声明：本回测仅供参考，不构成投资建议")
        print("=" * 60 + "\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="TimesFM 预测准确率回测")
    parser.add_argument(
        "--stocks",
        type=str,
        default="600519",
        help="股票代码（默认：600519）",
    )
    parser.add_argument(
        "--test-days",
        type=int,
        default=30,
        help="回测天数（默认：30）",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=5,
        help="每次预测天数（默认：5）",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=252,
        help="上下文长度（默认：252，约1年）",
    )

    args = parser.parse_args()

    # 支持多股票
    stock_codes = args.stocks.split(",")

    for stock_code in stock_codes:
        try:
            print(f"\n{'='*60}")
            print(f"开始回测 {stock_code}...")
            print(f"{'='*60}\n")

            backtester = TimesFMBacktester(
                stock_code=stock_code.strip(),
                test_days=args.test_days,
                forecast_horizon=args.horizon,
                context_length=args.context,
            )

            # 获取历史数据
            df = backtester.fetch_historical_data()

            # 运行回测
            metrics = backtester.run_backtest(df)

            # 打印报告
            if metrics:
                backtester.print_report(metrics)
            else:
                print(f"❌ {stock_code} 回测失败")

        except Exception as e:
            logger.error(f"回测 {stock_code} 时出错: {e}", exc_info=True)
            continue


if __name__ == "__main__":
    main()
