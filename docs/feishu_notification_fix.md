# 飞书机器人通知配置问题总结报告

## 问题概述

在配置 `daily_stock_analysis` 项目的飞书机器人通知功能时，遇到了两种验证方式的配置问题，导致通知发送失败。

## 问题现象

- **关键字验证**：返回错误码 `19024 - Key Words Not Found`
- **签名验证**：返回错误码 `19021 - sign match fail or timestamp is not within one hour from current time`

## 排查过程

### 第一阶段：关键字验证

**尝试方案：**
1. 在消息内容前添加关键字（`股票 分析`）
2. 使用换行符分隔关键字
3. 跳过卡片格式，直接使用文本格式

**问题根因：**
- 代码中 `hmac.new` 参数顺序错误

### 第二阶段：签名验证

**文档要求：**
- 签名算法：`HmacSHA256(timestamp + "\n" + secret)`
- 签名需要放在 **JSON 请求体**中（不是 URL 参数）
- 时间戳需要是字符串类型

**修复关键点：**
```python
# 错误写法（之前）
hmac.new(secret.encode(), string_to_sign.encode())

# 正确写法（参考官方文档）
hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256)
```

**请求体格式：**
```json
{
    "msg_type": "text",
    "content": {"text": "..."},
    "timestamp": "1772850866",
    "sign": "ZbNvp7lgs1ohJIRlVTYKY0i+..."
}
```

## 代码修改

### 1. `src/config.py`
- 添加 `feishu_secret` 配置项

### 2. `src/notification_sender/feishu_sender.py`
- 添加签名生成方法 `_generate_sign()`
- 修改请求体构建逻辑，添加 `timestamp` 和 `sign` 字段
- 支持关键字和签名两种验证方式

### 3. `.env` 配置示例
```bash
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx
FEISHU_KEYWORDS=股票
FEISHU_SECRET=your_secret_key
```

## 经验教训

1. **优先参考官方文档**：飞书官方文档明确说明了签名需要放在 JSON 请求体中，而不是 URL 参数

2. **hmac.new 参数顺序**：
   - Python 标准库：`hmac.new(key, message, digestmod)`
   - 不是：`hmac.new(message, key, digestmod)`

3. **时间戳类型**：飞书要求 `timestamp` 是字符串类型

4. **两种验证方式**：
   - 关键字验证：简单，但消息格式受限
   - 签名验证：更安全，支持任意消息格式

## 最终效果

- ✅ 邮件通知正常
- ✅ 飞书通知正常
- ✅ 支持签名验证
- ✅ 支持关键字验证（已修复）
