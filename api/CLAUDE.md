[根目录](../CLAUDE.md) > **api**

## API 模块

> 更新时间：2026-03-05 11:05:33

### 模块职责

FastAPI 后端服务模块，提供 REST API 接口，用于：
- 股票分析触发与查询
- 历史记录查询
- 股票数据获取
- 系统配置管理

### 入口与启动

**启动方式：**
```bash
python main.py --serve  # 启动服务 + 执行分析
python main.py --serve-only  # 仅启动服务
```

**FastAPI 应用入口：** `api/app.py`

```python
from api.app import create_app
app = create_app()
```

### 目录结构

```
api/
├── app.py                    # FastAPI 应用工厂
├── deps.py                   # 依赖注入
├── middlewares/              # 中间件
│   ├── auth.py              # 认证中间件
│   └── error_handler.py     # 错误处理
└── v1/
    ├── router.py           # API 路由注册
    ├── endpoints/           # API 端点
    │   ├── agent.py        # Agent 对话
    │   ├── analysis.py     # 股票分析
    │   ├── auth.py         # 认证
    │   ├── backtest.py     # 回测
    │   ├── health.py       # 健康检查
    │   ├── history.py      # 历史记录
    │   ├── stocks.py       # 股票数据
    │   └── system_config.py # 系统配置
    └── schemas/            # Pydantic 模型
        ├── analysis.py
        ├── backtest.py
        ├── common.py
        ├── history.py
        ├── stocks.py
        └── system_config.py
```

### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/analysis/stock/{code}` | POST | 触发股票分析 |
| `/api/v1/history` | GET | 获取分析历史 |
| `/api/v1/stocks` | GET | 获取股票列表 |
| `/api/v1/stocks/extract-from-image` | POST | 从图片提取股票 |
| `/api/v1/backtest` | POST | 运行回测 |
| `/api/v1/system-config` | GET/PUT | 系统配置管理 |

### 关键依赖

- **FastAPI**: Web 框架
- **Uvicorn**: ASGI 服务器
- **Pydantic**: 数据验证
- **SQLAlchemy**: 数据库 ORM

### 认证配置

支持可选密码保护，在 `.env` 中设置 `ADMIN_AUTH_ENABLED=true` 启用。

### 相关文件

- 入口文件：`/Users/berton/Github/daily_stock_analysis/api/app.py`
- 路由配置：`/Users/berton/Github/daily_stock_analysis/api/v1/router.py`
- 测试文件：`tests/test_auth_api.py`, `tests/test_system_config_api.py`
