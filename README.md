<h1 align="center">Kiro API Proxy</h1>

<p align="center">
  Kiro IDE API 反向代理服务器，支持多账号轮询、Token 自动刷新、配额管理
</p>

<p align="center">
  <a href="#功能特性">功能</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#配置">配置</a> •
  <a href="#api-端点">API</a> •
  <a href="#许可证">许可证</a> •
  <a href="#免责声明">免责声明</a>
</p>

<p align="center">
  <strong>中文</strong> | <a href="README_EN.md">English</a>
</p>

---

> **⚠️ 说明**
>
> 本项目支持 **Claude Code**、**Codex CLI**、**Gemini CLI** 三种客户端，工具调用功能已全面支持。

## 功能特性

### 核心功能
- **多协议支持** — OpenAI / Anthropic / Gemini 三种协议兼容
- **完整工具调用** — 三种协议的工具调用功能全面支持
- **图片理解** — 支持 Claude Code / Codex CLI 图片输入
- **网络搜索** — 支持 Claude Code / Codex CLI 网络搜索工具
- **多账号轮询** — 支持添加多个 Kiro 账号，自动负载均衡
- **会话粘性** — 同一会话 60 秒内使用同一账号，保持上下文
- **Web UI** — 简洁的管理界面，支持监控、日志、设置
- **多语言界面** — 支持中文和英文界面切换

### 日志与监控
- **结构化日志** — 基于 loguru，控制台彩色输出 + 文件日志轮转
- **API 调用持久化** — JSONL 格式记录完整请求/响应（`data/logs/flows/`）
- **Sentry 集成** — 可选的 Sentry 错误追踪（ERROR+ 级别自动上报）

### 配置管理
- **TOML 配置文件** — `data/settings.toml`，首次启动自动生成默认配置
- **配置项** — 端口、限速、Sentry DSN、日志级别 / 轮转 / 保留天数等

### 历史消息管理
- **自动截断** — 优先保留最新上下文并摘要前文，必要时按数量/字符数截断
- **智能摘要** — 用 AI 生成早期对话摘要，保留关键信息（带缓存）
- **错误重试** — 遇到长度错误时自动截断重试（默认启用）
- **预估检测** — 预估 token 数量，超限预先截断

## 更新日志

### v1.8.0
- **持久化日志系统** — 基于 loguru，替换全部 print() 调用
  - 控制台彩色输出 + 文件日志每日轮转（`data/logs/kiro-proxy.log`）
  - API 调用 JSONL 持久化，记录完整请求/响应（`data/logs/flows/`）
- **Sentry 集成** — 可选的错误追踪，ERROR+ 级别自动上报
- **TOML 配置文件** — `data/settings.toml`，首次启动自动生成默认配置
  - 支持端口、限速、Sentry DSN、日志级别/轮转/保留天数等
- **运行时数据统一** — 配置、日志、凭证统一存放在项目 `data/` 目录下
- **kiro-account-manager 导入** — 支持导入 kiro-account-manager 格式的账号
- **模型映射更新** — 新增 claude-opus-4.6 模型，claude-opus-4.6 回退到 claude-opus-4.5（Kiro 免费版暂不支持 4.6）
- **精确 Token 统计** — 从 event-stream 提取 contextUsagePercentage，计算真实 input/output tokens
- **Thinking 模式** — 支持 Anthropic thinking 参数，自动转为 system prompt 前缀并解析 `<thinking>` 标签
- **web_search 可配置** — 新增 `web_search_enabled` 配置项，默认关闭（Kiro API 不支持 webSearchTool 格式）
- **流式响应修复** — 修复 Python 3.14 作用域冲突 + 缓冲区增量解析，解决流式内容提取为空的问题
- **httpx → curl-cffi** — 全面替换 HTTP 库
- **项目清理** — 移除 tkinter 启动器、PyInstaller 兼容代码和无用文件
- **构建系统** — 添加 `[build-system]`，支持 `uv sync` 安装 CLI 入口点
- **调试工具** — 抓包/测试脚本整理到 `scripts/` 目录
- **文档更新** — README、快速开始、部署指南全面更新

### v1.7.2
- **多语言支持** — WebUI 完整支持中英文切换
- **英文帮助文档** — 全部 5 篇文档已翻译为英文

### v1.6.3
- **命令行工具 (CLI)** — 无 GUI 服务器也能轻松管理
  - `accounts list/export/import/add/scan` — 账号管理
  - `login google/github/remote` — 登录
- **远程登录链接** — 在有浏览器的机器上完成授权，Token 自动同步
- **账号导入导出** — 跨机器迁移账号配置

### v1.6.2
- **Codex CLI 完整支持** — OpenAI Responses API (`/v1/responses`)
  - 完整工具调用、图片输入、网络搜索、错误代码映射
- **Claude Code 增强** — 图片理解和网络搜索完整支持

### v1.6.1
- **请求限速** — 每账号最小请求间隔、每分钟最大请求数
- **账号封禁检测** — 自动检测并禁用被封禁账号
- **统一错误处理** — 三种协议使用统一的错误分类

### v1.6.0
- **历史消息管理** — 4 种策略处理对话长度限制
- **Gemini 工具调用** — 完整支持 functionDeclarations
- **设置页面** — WebUI 新增设置标签页

### v1.5.0
- **用量查询** — 查询账号配额使用情况
- **多登录方式** — Google / GitHub / AWS Builder ID
- **流量监控** — 完整的 LLM 请求监控
- **浏览器选择** — 自动检测已安装浏览器，支持无痕模式
- **文档中心** — 内置帮助文档

### v1.4.0
- **Token 预刷新** — 后台每 5 分钟检查，提前 15 分钟自动刷新
- **健康检查** — 每 10 分钟检测账号可用性
- **请求重试机制** — 网络错误/5xx 自动重试，指数退避

## 工具调用支持

| 功能 | Anthropic (Claude Code) | OpenAI (Codex CLI) | Gemini |
|------|------------------------|-------------------|--------|
| 工具定义 | ✅ `tools` | ✅ `tools.function` | ✅ `functionDeclarations` |
| 工具调用响应 | ✅ `tool_use` | ✅ `tool_calls` | ✅ `functionCall` |
| 工具结果 | ✅ `tool_result` | ✅ `tool` 角色消息 | ✅ `functionResponse` |
| 强制工具调用 | ✅ `tool_choice` | ✅ `tool_choice` | ✅ `toolConfig.mode` |
| 工具数量限制 | ✅ 50 个 | ✅ 50 个 | ✅ 50 个 |
| 历史消息修复 | ✅ | ✅ | ✅ |
| 图片理解 | ✅ | ✅ | ❌ |
| 网络搜索 | ✅ | ✅ | ❌ |

## 快速开始

### 环境要求

- **Python** ≥ 3.14
- **[uv](https://docs.astral.sh/uv/)** — Python 包管理器

### 安装运行

```bash
# 克隆项目
git clone https://github.com/your-username/KiroProxy.git
cd KiroProxy

# 安装依赖
uv sync

# 运行（默认端口 8080）
uv run python run.py

# 指定端口
uv run python run.py 9090
```

启动后访问 http://localhost:8080 打开管理界面。

### 命令行工具 (CLI)

```bash
# 账号管理
uv run python run.py accounts list              # 列出账号
uv run python run.py accounts export -o acc.json # 导出账号
uv run python run.py accounts import acc.json    # 导入账号
uv run python run.py accounts add                # 交互式添加 Token
uv run python run.py accounts scan --auto        # 扫描并自动添加本地 Token

# 登录
uv run python run.py login google                # Google 登录
uv run python run.py login github                # GitHub 登录
uv run python run.py login remote --host myserver.com:8080  # 远程登录链接

# 服务
uv run python run.py serve                       # 启动服务 (默认 8080)
uv run python run.py serve -p 8081               # 指定端口
uv run python run.py status                      # 查看状态
```

### 获取 Token

**方式一：在线登录（推荐）**
1. 打开 Web UI，点击「在线登录」
2. 选择登录方式：Google / GitHub / AWS Builder ID
3. 在浏览器中完成授权，账号自动添加

**方式二：扫描 Token**
1. 打开 Kiro IDE 并登录
2. 在 Web UI 点击「扫描 Token」添加账号

## 配置

### 配置文件

首次启动自动生成 `data/settings.toml`：

```toml
[server]
port = 8080

[proxy]
quota_cooldown_seconds = 300
web_search_enabled = false
request_timeout = 300
max_retries = 2
max_flows = 500

[sentry]
dsn = ""
environment = "production"
traces_sample_rate = 0.1

[logging]
level = "INFO"
dir = "data/logs"
rotation = "00:00"
retention = "30 days"
api_log_enabled = true
api_log_max_body_chars = 50000
```

### 客户端配置

#### 模型对照表

| Kiro 模型 | 能力 | Claude Code | Codex |
|-----------|------|-------------|-------|
| `claude-sonnet-4` | ⭐⭐⭐ 推荐 | `claude-sonnet-4` | `gpt-4o` |
| `claude-sonnet-4.5` | ⭐⭐⭐⭐ 更强 | `claude-sonnet-4.5` | `gpt-4o` |
| `claude-haiku-4.5` | ⚡ 快速 | `claude-haiku-4.5` | `gpt-4o-mini` |
| `claude-opus-4.5` | ⭐⭐⭐⭐⭐ 最强 | `claude-opus-4.5` | `o1` |

#### Claude Code

```
名称: Kiro Proxy
API Key: any
Base URL: http://localhost:8080
模型: claude-sonnet-4
```

#### Codex CLI

```bash
export OPENAI_API_KEY=any
export OPENAI_BASE_URL=http://localhost:8080/v1
codex
```

或在 `~/.codex/config.toml` 中配置：

```toml
[providers.openai]
api_key = "any"
base_url = "http://localhost:8080/v1"
```

## API 端点

| 协议 | 端点 | 用途 |
|------|------|------|
| OpenAI | `POST /v1/chat/completions` | Chat Completions API |
| OpenAI | `POST /v1/responses` | Responses API (Codex CLI) |
| OpenAI | `GET /v1/models` | 模型列表 |
| Anthropic | `POST /v1/messages` | Claude Code |
| Anthropic | `POST /v1/messages/count_tokens` | Token 计数 |
| Gemini | `POST /v1/models/{model}:generateContent` | Gemini CLI |

### 管理 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/accounts` | GET | 获取所有账号状态 |
| `/api/accounts` | POST | 添加账号 |
| `/api/accounts/{id}` | GET | 获取账号详情 |
| `/api/accounts/{id}` | DELETE | 删除账号 |
| `/api/accounts/{id}/toggle` | POST | 启用/禁用账号 |
| `/api/accounts/{id}/refresh` | POST | 刷新账号 Token |
| `/api/accounts/{id}/restore` | POST | 恢复账号（从冷却状态） |
| `/api/accounts/{id}/usage` | GET | 获取账号用量信息 |
| `/api/accounts/refresh-all` | POST | 刷新所有即将过期的 Token |
| `/api/accounts/export` | GET | 导出账号配置 |
| `/api/accounts/import` | POST | 导入账号配置 |
| `/api/accounts/manual` | POST | 手动添加 Token |
| `/api/token/scan` | GET | 扫描本地 Token 文件 |
| `/api/token/add-from-scan` | POST | 从扫描结果添加账号 |
| `/api/token/refresh-check` | POST | 检查 Token 刷新状态 |
| `/api/flows` | GET | 获取流量记录 |
| `/api/flows/stats` | GET | 获取流量统计 |
| `/api/flows/{id}` | GET | 获取流量详情 |
| `/api/flows/{id}/bookmark` | POST | 收藏流量记录 |
| `/api/flows/{id}/note` | POST | 添加备注 |
| `/api/flows/{id}/tag` | POST | 添加标签 |
| `/api/flows/export` | POST | 导出流量记录 |
| `/api/quota` | GET | 获取配额状态 |
| `/api/stats` | GET | 获取统计信息 |
| `/api/stats/detailed` | GET | 获取详细统计 |
| `/api/health-check` | POST | 手动触发健康检查 |
| `/api/browsers` | GET | 获取可用浏览器列表 |
| `/api/settings/history` | GET/POST | 历史消息管理设置 |
| `/api/settings/rate-limit` | GET/POST | 请求限速设置 |
| `/api/docs` | GET | 获取文档列表 |
| `/api/docs/{id}` | GET | 获取文档内容 |
| `/api/kiro/login/start` | POST | 启动 AWS 登录 |
| `/api/kiro/login/poll` | GET | 轮询登录状态 |
| `/api/kiro/social/*` | POST/GET | Social Auth 登录 |
| `/api/remote-login/*` | POST/GET | 远程登录链接 |

## 项目结构

```
KiroProxy/
├── run.py                         # 启动入口
├── pyproject.toml                 # 项目依赖
│
├── kiro_proxy/
│   ├── main.py                    # FastAPI 应用
│   ├── config.py                  # 全局配置（模型映射等）
│   ├── converters.py              # 协议转换
│   ├── cli.py                     # 命令行工具
│   ├── kiro_api.py                # Kiro API 客户端
│   │
│   ├── core/                      # 核心模块
│   │   ├── settings.py            # TOML 配置文件管理
│   │   ├── logger.py              # loguru 日志模块
│   │   ├── flow_monitor.py        # 流量监控 + JSONL 持久化
│   │   ├── account.py             # 账号管理
│   │   ├── state.py               # 全局状态
│   │   ├── persistence.py         # 账号持久化
│   │   ├── scheduler.py           # 后台任务调度
│   │   ├── retry.py               # 重试机制
│   │   ├── history_manager.py     # 历史消息管理
│   │   └── ...
│   │
│   ├── credential/                # 凭证管理
│   │   ├── fingerprint.py         # Machine ID
│   │   ├── quota.py               # 配额管理
│   │   └── refresher.py           # Token 刷新
│   │
│   ├── auth/                      # 认证模块
│   │   └── device_flow.py         # Device Code Flow / Social Auth
│   │
│   ├── handlers/                  # API 处理器
│   │   ├── anthropic.py           # /v1/messages
│   │   ├── openai.py              # /v1/chat/completions
│   │   ├── responses.py           # /v1/responses (Codex CLI)
│   │   ├── gemini.py              # Gemini 协议
│   │   └── admin.py               # 管理 API
│   │
│   ├── docs/                      # 内置帮助文档
│   └── web/                       # Web UI
│
├── scripts/                       # 调试工具（见 scripts/README.md）
│
└── data/                          # 运行时数据（gitignored）
    ├── settings.toml              # 应用配置
    ├── accounts.json              # 账号列表
    ├── tokens/                    # 凭证文件
    └── logs/
        ├── kiro-proxy.log         # 应用日志
        └── flows/
            └── YYYY-MM-DD.jsonl   # API 调用记录
```

## 许可证

本项目采用 [MIT License](LICENSE) 开源。

## 免责声明

本项目仅供学习研究，禁止商用。使用本项目产生的任何后果由使用者自行承担，与作者无关。

本项目与 Kiro / AWS / Anthropic 官方无关。
