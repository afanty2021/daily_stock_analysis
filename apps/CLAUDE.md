[根目录](../CLAUDE.md) > **apps**

## 应用模块

> 更新时间：2026-03-07 14:49:00

### 模块职责

桌面端和 Web 端应用程序，包含：
- Web 管理界面 (React + TypeScript)
- 桌面客户端 (Electron)

### 目录结构

```
apps/
├── dsa-web/                 # Web 管理界面
│   ├── src/
│   │   ├── App.tsx         # 主应用组件
│   │   ├── api/            # API 客户端
│   │   │   ├── agent.ts
│   │   │   ├── analysis.ts
│   │   │   ├── auth.ts
│   │   │   ├── backtest.ts
│   │   │   ├── history.ts
│   │   │   ├── stocks.ts
│   │   │   └── systemConfig.ts
│   │   ├── components/     # React 组件
│   │   │   ├── common/     # 通用组件
│   │   │   └── settings/   # 设置组件
│   │   │       └── LLMChannelEditor.tsx  # LLM 渠道编辑器
│   │   └── assets/          # 静态资源
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
└── dsa-desktop/             # 桌面客户端
    ├── main.js             # 主进程
    ├── preload.js          # 预加载脚本
    └── renderer/           # 渲染进程
```

### Web 界面功能

- 配置管理（系统设置、通知渠道）
- LLM 多渠道配置（支持 AIHubmix、DeepSeek、通义千问、智谱 GLM、Moonshot、硅基流动等）
- 手动触发股票分析
- 查看分析历史记录
- 回测结果查看
- 从图片添加股票

### 核心组件

#### LLMChannelEditor.tsx
LLM 渠道编辑器组件，用于在 Web 界面配置多个 LLM 渠道。

**支持的渠道预设：**
- AIHubmix（聚合平台）
- DeepSeek 官方
- 通义千问（Dashscope）
- 智谱 GLM
- Moonshot（月之暗面）
- 硅基流动（SiliconFlow）
- OpenRouter
- Gemini（原生）
- 自定义渠道

**功能特性：**
- 渠道添加/删除/编辑
- API Key 可见性切换
- 独立保存渠道配置
- 与其他配置项分离管理

### 构建与启动

```bash
# Web 应用
cd apps/dsa-web
npm install
npm run dev

# 构建生产版本
npm run build

# 桌面客户端
cd apps/dsa-desktop
npm install
npm run build
```

### 技术栈

- **前端框架**: React 18
- **构建工具**: Vite
- **桌面框架**: Electron
- **语言**: TypeScript

### 相关文件

- Web 入口：`/Users/berton/Github/daily_stock_analysis/apps/dsa-web/src/App.tsx`
- LLM 渠道编辑器：`/Users/berton/Github/daily_stock_analysis/apps/dsa-web/src/components/settings/LLMChannelEditor.tsx`
- 桌面主进程：`/Users/berton/Github/daily_stock_analysis/apps/dsa-desktop/main.js`
- 打包文档：`/Users/berton/Github/daily_stock_analysis/docs/desktop-package.md`

### 变更记录

#### 2026-03-07 - LLM 渠道编辑器新增
- 新增 LLMChannelEditor.tsx 组件
- 支持 9 种渠道预设配置
- 添加 API Key 可见性切换
- 实现渠道独立保存机制
