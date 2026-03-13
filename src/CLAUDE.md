[根目录](../CLAUDE.md) > **src**

## 核心业务模块

> 更新时间：2026-03-13 08:00:00

### 模块职责

项目核心业务逻辑模块，包含：
- 股票分析与 AI 分析器
- Agent 策略对话系统
- 通知服务
- 数据存储
- 回测引擎
- 配置注册表

### 入口与启动

**主入口：** `main.py`

```python
from src.core.pipeline import StockAnalysisPipeline

# 创建分析流水线
pipeline = StockAnalysisPipeline(config=config)
results = pipeline.run(stock_codes=['600519'])
```

### 目录结构

```
src/
├── agent/                    # AI Agent 系统
│   ├── executor.py          # Agent 执行器
│   ├── factory.py          # Agent 工厂
│   ├── llm_adapter.py      # LLM 适配器
│   ├── conversation.py     # 对话管理
│   ├── tools/              # Agent 工具
│   │   ├── analysis_tools.py
│   │   ├── data_tools.py
│   │   ├── market_tools.py
│   │   ├── search_tools.py
│   │   └── registry.py
│   └── skills/             # Agent 技能
│       └── base.py
├── core/                    # 核心引擎
│   ├── pipeline.py         # 分析流水线
│   ├── backtest_engine.py  # 回测引擎
│   ├── market_review.py    # 大盘复盘
│   ├── market_strategy.py  # 市场策略
│   ├── trading_calendar.py # 交易日历
│   ├── config_manager.py   # 配置管理
│   └── config_registry.py # 配置字段元数据注册表
├── data/                    # 数据模块
│   ├── __init__.py
│   └── stock_mapping.py    # 股票映射
├── schemas/                 # 数据验证 Schema
│   ├── __init__.py
│   └── report_schema.py    # 报告 Schema（Pydantic）
├── services/                # 业务服务
│   ├── analysis_service.py  # 分析服务
│   ├── backtest_service.py # 回测服务
│   ├── system_config_service.py # 系统配置服务
│   ├── history_service.py  # 历史服务
│   ├── history_comparison_service.py # 历史对比服务
│   ├── image_stock_extractor.py # 图片股票提取
│   ├── import_parser.py    # 导入解析器
│   ├── name_to_code_resolver.py # 名称→代码解析
│   ├── report_renderer.py  # 报告渲染器
│   └── stock_code_utils.py # 股票代码工具
├── notification.py          # 通知服务入口
├── notification_sender/     # 通知渠道
│   ├── email_sender.py
│   ├── feishu_sender.py
│   ├── telegram_sender.py
│   ├── discord_sender.py
│   └── ...
├── analyzer.py              # AI 分析器
├── stock_analyzer.py        # 趋势分析器
├── market_analyzer.py       # 大盘分析器
├── search_service.py        # 搜索服务
├── storage.py               # 数据存储
├── config.py                # 配置管理
├── formatters.py            # 格式化工具
└── enums.py                 # 枚举定义
```

### 核心组件

#### 1. StockAnalysisPipeline (pipeline.py)
- 协调整个分析流程
- 断点续传机制
- 并发控制

#### 2. GeminiAnalyzer (analyzer.py)
- AI 分析生成决策建议
- 支持 Gemini/OpenAI/Claude 多模型
- `generate_text()` 方法提供统一文本生成接口

#### 3. StockTrendAnalyzer (stock_analyzer.py)
- MA 多头排列判断
- 技术指标计算

#### 4. MarketAnalyzer (market_analyzer.py)
- 大盘复盘分析
- 调用 `generate_text()` 与 AI 分析器交互

#### 5. NotificationService (notification.py)
- 多渠道通知发送
- 消息格式化

#### 6. ConfigRegistry (config_registry.py)
- 配置字段元数据注册表
- 提供配置 UI 元数据、验证提示和分类分组
- 支持的配置类别：base, ai_model, data_source, notification, system, agent, backtest

### 配置注册表 (config_registry.py)

**配置类别：**
| 类别 | 标题 | 说明 |
|------|------|------|
| base | Base Settings | 自选股和基础应用设置 |
| ai_model | AI Model | 模型提供商、模型名称、推理参数 |
| data_source | Data Source | 市场数据提供商凭证和优先级设置 |
| notification | Notification | 机器人、Webhook 和推送渠道设置 |
| system | System | 运行时和调度控制 |
| agent | Agent | Agent 模式和策略设置 |
| backtest | Backtest | 回测引擎行为和评估参数 |

**关键配置字段：**
- `STOCK_LIST`: 自选股列表
- `LITELLM_MODEL`: 主模型（LiteLLM 格式）
- `LITELLM_FALLBACK_MODELS`: 备用模型列表
- `LITELLM_CONFIG`: LiteLLM 配置文件路径
- `LLM_CHANNELS`: LLM 渠道名称
- `DEEPSEEK_API_KEY`: DeepSeek API 密钥
- `TUSHARE_TOKEN`: Tushare 令牌
- `REALTIME_SOURCE_PRIORITY`: 实时数据源优先级

### 关键依赖

- **litellm**: 多模型统一调用
- **akshare**: 金融数据获取
- **pandas**: 数据处理
- **sqlalchemy**: 数据库
- **pyyaml**: 配置文件解析

### 测试

```bash
pytest tests/test_agent_executor.py -v
pytest tests/test_backtest_engine.py -v
pytest tests/test_notification.py -v
pytest tests/test_config_validate_structured.py -v
pytest tests/test_market_analyzer_generate_text.py -v
```

### 相关文件

- 主入口：`/Users/berton/Github/daily_stock_analysis/main.py`
- 核心配置：`/Users/berton/Github/daily_stock_analysis/src/config.py`
- 配置注册表：`/Users/berton/Github/daily_stock_analysis/src/core/config_registry.py`
- 测试目录：`/Users/berton/Github/daily_stock_analysis/tests/`

### 变更记录

#### 2026-03-13 - 配置引擎重构与数据源韧性 (v3.5.0)
- **配置引擎重构**: `src/core/config_manager.py` 大幅扩展，统一配置管理
- **Agent 模型服务**: `src/services/agent_model_service.py` 新增模型发现 API
- **历史服务增强**: `src/services/history_service.py` 大幅扩展，支持 Markdown 报告导出
- **股票映射增强**: `src/data/stock_mapping.py` 新增 STOOQ 映射
- **Agent 工具增强**: `src/agent/tools/analysis_tools.py` analyze_trend 修复
- **测试**: 新增 `test_config_manager.py` 和 `test_agent_models_api.py`

#### 2026-03-12 - SearXNG 搜索与筹码结构兜底
- **搜索服务增强**: `src/search_service.py` 新增 SearXNG 支持（配额免费兜底选项）
- **analyzer 增强**: 新增筹码结构 (`chip_structure`) 兜底补全逻辑
- **配置管理**: `src/config.py` 新增 GitHub Actions 相关配置
- **测试**: 新增 `test_chip_structure_fallback.py` 和 `test_search_searxng.py`

#### 2026-03-10 - 报告引擎 P0 与智能导入
- **新增模块**:
  - `src/data/` - 数据模块（股票映射）
  - `src/schemas/` - Pydantic Schema 模块（report_schema.py）
  - `src/services/import_parser.py` - CSV/Excel 导入解析
  - `src/services/name_to_code_resolver.py` - 名称→代码解析引擎
  - `src/services/history_comparison_service.py` - 历史对比服务
  - `src/services/report_renderer.py` - Jinja2 报告渲染器
  - `src/services/stock_code_utils.py` - 股票代码工具
- **报告引擎 P0**: Pydantic schema 验证、Jinja2 模板、完整性校验、Brief 模式
- **智能导入**: Vision LLM 提取代码+名称+置信度，多源导入（图片/CSV/Excel/剪贴板）
- **LLM Token 跟踪**: 所有 LLM 调用记录到 `llm_usage` 表
- **Agent 增强**: 导出会话、发送到通知渠道、后台执行
- **测试覆盖**: 新增 13 个测试文件

#### 2026-03-07 - 配置注册表与测试更新
- 新增 config_registry.py 配置字段元数据注册表
- 新增测试 test_config_validate_structured.py
- 新增测试 test_market_analyzer_generate_text.py
- 添加 `generate_text()` 统一接口用于 AI 分析
- 添加多渠道 LLM 配置支持
