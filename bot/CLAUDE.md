[根目录](../CLAUDE.md) > **bot**

## 机器人模块

> 更新时间：2026-03-05 11:05:33

### 模块职责

多平台机器人集成模块，支持：
- 命令处理
- 消息交互
- 事件订阅

### 目录结构

```
bot/
├── __init__.py              # 模块入口
├── handler.py               # 消息处理入口
├── dispatcher.py            # 命令分发器
├── models.py                # 数据模型
├── commands/                # 命令实现
│   ├── base.py             # 基类
│   ├── analyze.py          # 分析命令
│   ├── ask.py              # 问答命令
│   ├── batch.py            # 批量分析
│   ├── chat.py             # 对话
│   ├── help.py             # 帮助
│   ├── market.py           # 大盘
│   └── status.py           # 状态
└── platforms/              # 平台集成
    ├── base.py             # 基类
    ├── dingtalk.py         # 钉钉
    ├── dingtalk_stream.py  # 钉钉 Stream
    ├── discord.py          # Discord
    └── feishu_stream.py    # 飞书 Stream
```

### 支持平台

| 平台 | 消息 | 事件订阅 | Webhook |
|------|------|---------|---------|
| **Telegram** | ✅ | ✅ | ✅ |
| **Discord** | ✅ | ✅ | ✅ |
| **飞书** | ✅ | ✅ | ✅ |
| **钉钉** | ✅ | ✅ | ✅ |
| **企业微信** | ✅ | - | ✅ |

### 命令列表

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/analyze <code>` | 分析指定股票 |
| `/ask <code> [strategy]` | Agent 策略问答 |
| `/batch <codes>` | 批量分析 |
| `/market [cn/us]` | 大盘复盘 |
| `/status` | 系统状态 |

### 配置示例

```bash
# Telegram
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

# Discord
DISCORD_BOT_TOKEN=xxx
DISCORD_MAIN_CHANNEL_ID=xxx

# 飞书
FEISHU_APP_ID=xxx
FEISHU_APP_SECRET=xxx

# 钉钉
DINGTALK_APP_KEY=xxx
DINGTALK_APP_SECRET=xxx
```

### 相关文件

- 消息处理：`/Users/berton/Github/daily_stock_analysis/bot/handler.py`
- 文档目录：`/Users/berton/Github/daily_stock_analysis/docs/bot/`
