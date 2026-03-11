[根目录](../CLAUDE.md) > **strategies**

## Agent 策略模块

> 更新时间：2026-03-05 11:05:33

### 模块职责

AI Agent 内置交易策略定义，支持自然语言问答形式的策略分析。

### 内置策略

| 策略 | 文件 | 说明 |
|------|------|------|
| **均线金叉** | `ma_golden_cross.yaml` | MA5 上穿 MA10 买入信号 |
| **缠论** | `chan_theory.yaml` | 基于缠中说禅理论的走势分析 |
| **波浪理论** | `wave_theory.yaml` | 艾略特波浪理论分析 |
| **多头趋势** | `bull_trend.yaml` | MA5 > MA10 > MA20 判断 |
| **龙头股** | `dragon_head.yaml` | 行业龙头股识别 |
| **缩量回踩** | `shrink_pullback.yaml` | 缩量回调支撑位买入 |
| **放量突破** | `volume_breakout.yaml` | 放量突破压力位 |
| **底部放量** | `bottom_volume.yaml` | 底部堆量反转信号 |
| **箱体震荡** | `box_oscillation.yaml` | 区间震荡高抛低吸 |
| **情绪周期** | `emotion_cycle.yaml` | 市场情绪周期分析 |
| **一阳三阴** | `one_yang_three_yin.yaml` | 回调后反转信号 |

### 使用方式

```bash
# 启用 Agent 模式
AGENT_MODE=true

# 激活所有策略
AGENT_SKILLS=all

# 或指定策略
AGENT_SKILLS=ma_golden_cross,chan_theory
```

### Agent 命令

```
/ask 600519 ma_golden_cross    # 用均线金叉策略分析
/ask 600519 chan_theory       # 用缠论分析
/ask AAPL wave_theory         # 波浪理论分析美股
```

### 自定义策略

在 `strategies/` 目录下新建 YAML 文件：

```yaml
name: "我的策略"
description: "自定义策略描述"
indicators:
  - name: "MA5"
    type: "ma"
    params: [5]
signals:
  - name: "买入信号"
    condition: "MA5 > MA10"
```

### 策略配置目录

```bash
# 自定义策略目录
AGENT_STRATEGY_DIR=./my_strategies
```

### 相关文件

- 策略目录：`/Users/berton/Github/daily_stock_analysis/strategies/`
- Agent 执行器：`/Users/berton/Github/daily_stock_analysis/src/agent/executor.py`
- 工具注册：`/Users/berton/Github/daily_stock_analysis/src/agent/tools/registry.py`
