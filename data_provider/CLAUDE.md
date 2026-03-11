[根目录](../CLAUDE.md) > **data_provider**

## 数据源模块

> 更新时间：2026-03-05 11:05:33

### 模块职责

多数据源行情获取模块，统一管理不同数据源，提供：
- 实时行情
- 历史 K 线
- 股票基本信息
- 板块数据
- 筹码分布

### 目录结构

```
data_provider/
├── __init__.py              # 模块入口
├── base.py                  # 基类定义
├── akshare_fetcher.py       # AkShare 数据源
├── tushare_fetcher.py       # Tushare 数据源
├── yfinance_fetcher.py     # Yahoo Finance 数据源
├── efinance_fetcher.py     # EFinance 数据源
├── baostock_fetcher.py     # BaoStock 数据源
├── pytdx_fetcher.py        # Pytdx 数据源
├── realtime_types.py        # 实时数据类型
└── us_index_mapping.py     # 美股指数映射
```

### 数据源

| 数据源 | 用途 | 备注 |
|--------|------|------|
| **Akshare** | A股/港股/期货数据 | 主要数据源 |
| **Tushare** | A股/期货数据 | 需要 Token |
| **Yahoo Finance** | 美股数据 | 免费 |
| **EFinance** | A股实时行情 | 东财接口 |
| **BaoStock** | A股历史数据 | 免费 |
| **Pytdx** | 期货/行情 | 兼容性好 |

### 核心类

**DataFetcherManager** (base.py)
- 统一管理多数据源
- 自动故障转移
- 断点续传

```python
from data_provider import DataFetcherManager

fetcher = DataFetcherManager()
df, source = fetcher.get_daily_data('600519', days=30)
```

### 实时行情配置

```bash
# 配置数据源优先级
REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em

# 启用/禁用
ENABLE_REALTIME_QUOTE=true
ENABLE_CHIP_DISTRIBUTION=true
```

### 相关文件

- 统一管理器：`/Users/berton/Github/daily_stock_analysis/data_provider/base.py`
- 测试文件：`/Users/berton/Github/daily_stock_analysis/tests/test_get_latest_data.py`
