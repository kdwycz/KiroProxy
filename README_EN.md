<h1 align="center">Kiro API Proxy</h1>

<p align="center">
  Kiro IDE API reverse proxy server with multi-account rotation, auto token refresh, and quota management
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#api-endpoints">API</a> •
  <a href="#license">License</a>
</p>

<p align="center">
  <a href="README.md">中文</a> | <strong>English</strong>
</p>

---

> **⚠️ Note**
>
> This project supports **Claude Code**, **Codex CLI**, and **Gemini CLI** clients with full tool calling support.

## Features

### Core
- **Multi-protocol** — OpenAI / Anthropic / Gemini API compatible
- **Full tool calling** — Complete support across all three protocols
- **Image understanding** — Claude Code / Codex CLI image input
- **Web search** — Claude Code / Codex CLI web search tools
- **Multi-account rotation** — Add multiple Kiro accounts with automatic load balancing
- **Session affinity** — Same account for 60s within a session for context continuity
- **Web UI** — Clean management dashboard with monitoring, logs, and settings
- **i18n** — Chinese and English UI

### Logging & Monitoring
- **Structured logging** — loguru-based, colored console + rotating file logs
- **API call persistence** — JSONL format with full request/response (`data/logs/flows/`)
- **Sentry integration** — Optional error tracking (ERROR+ level auto-reported)

### Configuration
- **TOML config file** — `data/settings.toml`, auto-generated on first run
- **Settings** — Port, rate limits, Sentry DSN, log level / rotation / retention, etc.

### History Management
- **Auto truncation** — Preserve recent context, summarize earlier messages
- **Smart summarization** — AI-generated summaries with caching
- **Error retry** — Auto-truncate and retry on length errors (default on)
- **Token estimation** — Pre-emptive truncation based on estimated token count

## Changelog

### v1.8.0
- **Persistent logging** — loguru-based, replacing all print() calls
  - Colored console + daily rotating file logs (`data/logs/kiro-proxy.log`)
  - JSONL API call persistence with full request/response (`data/logs/flows/`)
- **Sentry integration** — Optional error tracking, ERROR+ auto-reported
- **TOML config file** — `data/settings.toml`, auto-generated defaults
- **Unified runtime data** — Config, logs, credentials all under project `data/` directory
- **kiro-account-manager import** — Import accounts from kiro-account-manager format
- **Model mapping update** — Added claude-opus-4.6, falls back to claude-opus-4.5 (Kiro free tier doesn't support 4.6 yet)
- **Accurate token stats** — Extract contextUsagePercentage from event-stream for real input/output tokens
- **Thinking mode** — Anthropic thinking parameter support, auto-converted to system prompt prefix with `<thinking>` tag parsing
- **Configurable web_search** — New `web_search_enabled` setting, off by default (Kiro API doesn't support webSearchTool format)
- **Streaming fix** — Fixed Python 3.14 scoping conflict + buffered incremental parsing for empty stream content
- **httpx → curl-cffi** — Full HTTP library replacement for better compatibility
- **Project cleanup** — Removed tkinter launcher, PyInstaller compat, and unused files
- **Build system** — Added `[build-system]` for `uv sync` CLI entry point installation
- **Debug tools** — Moved capture/test scripts to `scripts/`
- **Documentation** — Full rewrite of README, quickstart, and deployment guides

### v1.7.2
- **i18n** — Full Chinese/English WebUI support
- **English docs** — All 5 help docs translated

### v1.6.3
- **CLI tool** — Manage accounts without GUI
- **Remote login** — Generate login links for headless servers
- **Account import/export** — Cross-machine migration

### v1.6.2
- **Codex CLI support** — OpenAI Responses API (`/v1/responses`)
- **Claude Code enhancement** — Image understanding and web search

### v1.6.1
- **Rate limiting** — Per-account request interval and rate limits
- **Ban detection** — Auto-detect and disable banned accounts
- **Unified error handling** — Consistent error classification across protocols

### v1.6.0
- **History management** — 4 strategies for conversation length limits
- **Gemini tool calling** — Full functionDeclarations support
- **Settings page** — WebUI settings tab

### v1.5.0
- **Usage query** — Check account quota usage
- **Multiple login methods** — Google / GitHub / AWS Builder ID
- **Traffic monitoring** — Full LLM request monitoring
- **Browser selection** — Auto-detect browsers, incognito mode support
- **Help center** — Built-in documentation

### v1.4.0
- **Token pre-refresh** — Background check every 5 min, auto-refresh 15 min before expiry
- **Health checks** — Every 10 min account availability check
- **Request retry** — Auto-retry on network errors/5xx with exponential backoff

## Tool Calling Support

| Feature | Anthropic (Claude Code) | OpenAI (Codex CLI) | Gemini |
|---------|------------------------|-------------------|--------|
| Tool definitions | ✅ `tools` | ✅ `tools.function` | ✅ `functionDeclarations` |
| Tool call response | ✅ `tool_use` | ✅ `tool_calls` | ✅ `functionCall` |
| Tool results | ✅ `tool_result` | ✅ `tool` role message | ✅ `functionResponse` |
| Force tool call | ✅ `tool_choice` | ✅ `tool_choice` | ✅ `toolConfig.mode` |
| Tool limit | ✅ 50 | ✅ 50 | ✅ 50 |
| History repair | ✅ | ✅ | ✅ |
| Image understanding | ✅ | ✅ | ❌ |
| Web search | ✅ | ✅ | ❌ |

## Quick Start

### Requirements

- **Python** ≥ 3.14
- **[uv](https://docs.astral.sh/uv/)** — Python package manager

### Installation

```bash
# Clone
git clone <your-repo-url>
cd KiroProxy

# Install dependencies
uv sync

# Run (default port 8080)
uv run python run.py

# Specify port
uv run python run.py 9090
```

Open http://localhost:8080 after startup.

### CLI Tool

```bash
# Account management
uv run python run.py accounts list
uv run python run.py accounts export -o acc.json
uv run python run.py accounts import acc.json
uv run python run.py accounts add
uv run python run.py accounts scan --auto

# Login
uv run python run.py login google
uv run python run.py login github
uv run python run.py login remote --host myserver.com:8080

# Service
uv run python run.py serve
uv run python run.py serve -p 8081
uv run python run.py status
```

### Getting Tokens

**Option 1: Online Login (Recommended)**
1. Open Web UI, click "Online Login"
2. Choose: Google / GitHub / AWS Builder ID
3. Complete authorization, account auto-added

**Option 2: Scan Tokens**
1. Open Kiro IDE and log in
2. Click "Scan Tokens" in Web UI

## Configuration

### Config File

Auto-generated at `data/settings.toml` on first run:

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

### Client Configuration

#### Model Mapping

| Kiro Model | Capability | Claude Code | Codex |
|-----------|------|-------------|-------|
| `claude-sonnet-4` | ⭐⭐⭐ Recommended | `claude-sonnet-4` | `gpt-4o` |
| `claude-sonnet-4.5` | ⭐⭐⭐⭐ Stronger | `claude-sonnet-4.5` | `gpt-4o` |
| `claude-haiku-4.5` | ⚡ Fast | `claude-haiku-4.5` | `gpt-4o-mini` |
| `claude-opus-4.5` | ⭐⭐⭐⭐⭐ Strongest | `claude-opus-4.5` | `o1` |

#### Claude Code

```
Name: Kiro Proxy
API Key: any
Base URL: http://localhost:8080
Model: claude-sonnet-4
```

#### Codex CLI

```bash
export OPENAI_API_KEY=any
export OPENAI_BASE_URL=http://localhost:8080/v1
codex
```

Or in `~/.codex/config.toml`:

```toml
[providers.openai]
api_key = "any"
base_url = "http://localhost:8080/v1"
```

## API Endpoints

| Protocol | Endpoint | Purpose |
|----------|----------|---------|
| OpenAI | `POST /v1/chat/completions` | Chat Completions API |
| OpenAI | `POST /v1/responses` | Responses API (Codex CLI) |
| OpenAI | `GET /v1/models` | Model list |
| Anthropic | `POST /v1/messages` | Claude Code |
| Anthropic | `POST /v1/messages/count_tokens` | Token counting |
| Gemini | `POST /v1/models/{model}:generateContent` | Gemini CLI |

### Management API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/accounts` | GET | List all accounts |
| `/api/accounts` | POST | Add account |
| `/api/accounts/{id}` | GET | Account details |
| `/api/accounts/{id}` | DELETE | Delete account |
| `/api/accounts/{id}/toggle` | POST | Enable/disable account |
| `/api/accounts/{id}/refresh` | POST | Refresh token |
| `/api/accounts/{id}/restore` | POST | Restore from cooldown |
| `/api/accounts/{id}/usage` | GET | Account usage info |
| `/api/accounts/refresh-all` | POST | Refresh all expiring tokens |
| `/api/accounts/export` | GET | Export accounts |
| `/api/accounts/import` | POST | Import accounts |
| `/api/accounts/manual` | POST | Manually add token |
| `/api/token/scan` | GET | Scan local token files |
| `/api/token/add-from-scan` | POST | Add from scan results |
| `/api/token/refresh-check` | POST | Check token refresh status |
| `/api/flows` | GET | Traffic records |
| `/api/flows/stats` | GET | Traffic statistics |
| `/api/flows/{id}` | GET | Flow details |
| `/api/flows/{id}/bookmark` | POST | Bookmark flow |
| `/api/flows/{id}/note` | POST | Add note |
| `/api/flows/{id}/tag` | POST | Add tag |
| `/api/flows/export` | POST | Export flows |
| `/api/quota` | GET | Quota status |
| `/api/stats` | GET | Statistics |
| `/api/stats/detailed` | GET | Detailed statistics |
| `/api/health-check` | POST | Manual health check |
| `/api/browsers` | GET | Available browsers |
| `/api/settings/history` | GET/POST | History management settings |
| `/api/settings/rate-limit` | GET/POST | Rate limit settings |
| `/api/docs` | GET | Documentation list |
| `/api/docs/{id}` | GET | Document content |
| `/api/kiro/login/start` | POST | Start AWS login |
| `/api/kiro/login/poll` | GET | Poll login status |
| `/api/kiro/social/*` | POST/GET | Social Auth login |
| `/api/remote-login/*` | POST/GET | Remote login links |

## Project Structure

```
KiroProxy/
├── run.py                         # Entry point
├── pyproject.toml                 # Dependencies
│
├── kiro_proxy/
│   ├── main.py                    # FastAPI app
│   ├── config.py                  # Global config (model mappings, etc.)
│   ├── converters.py              # Protocol conversion
│   ├── cli.py                     # CLI tool
│   ├── kiro_api.py                # Kiro API client
│   │
│   ├── core/                      # Core modules
│   │   ├── settings.py            # TOML config management
│   │   ├── logger.py              # loguru logging
│   │   ├── flow_monitor.py        # Traffic monitoring + JSONL persistence
│   │   ├── account.py             # Account management
│   │   ├── state.py               # Global state
│   │   ├── persistence.py         # Account persistence
│   │   ├── scheduler.py           # Background task scheduler
│   │   ├── retry.py               # Retry mechanism
│   │   ├── history_manager.py     # History message management
│   │   └── ...
│   │
│   ├── credential/                # Credential management
│   ├── auth/                      # Authentication (Device Code Flow / Social Auth)
│   ├── handlers/                  # API handlers (anthropic, openai, gemini, responses, admin)
│   ├── docs/                      # Built-in help docs
│   └── web/                       # Web UI
│
├── scripts/                       # Debug tools (see scripts/README.md)
│
└── data/                          # Runtime data (gitignored)
    ├── settings.toml
    ├── accounts.json
    ├── tokens/
    └── logs/
        ├── kiro-proxy.log
        └── flows/
            └── YYYY-MM-DD.jsonl
```

## License

This project is licensed under the [MIT License](LICENSE).

## Disclaimer

This project is for educational and research purposes only. Commercial use is prohibited. The author is not responsible for any consequences arising from the use of this project.

This project is not affiliated with Kiro / AWS / Anthropic.
