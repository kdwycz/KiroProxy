# Kiro 调试和测试工具

这些脚本用于调试 Kiro IDE 的 API 交互、抓包分析、接口测试等。

## 脚本列表

### capture_kiro.py — API 请求抓取

使用 mitmproxy 抓取 Kiro IDE 发送到 AWS 的请求，保存为 JSON 文件供分析。

**依赖:** `pip install mitmproxy`

**使用方式:**

```bash
# 方式 1: 作为 mitmproxy 插件运行（推荐）
mitmproxy -s scripts/capture_kiro.py
# 或无 UI 模式
mitmdump -s scripts/capture_kiro.py

# 方式 2: 查看帮助信息
python scripts/capture_kiro.py
```

**配置 Kiro IDE 代理:**
```bash
# 设置环境变量后启动 Kiro
export HTTPS_PROXY=http://127.0.0.1:8080
export HTTP_PROXY=http://127.0.0.1:8080
export NODE_TLS_REJECT_UNAUTHORIZED=0
```

抓取结果保存在 `kiro_requests/` 目录下。

---

### get_models.py — 查询 Kiro 可用模型

直接调用 Kiro API 的 `ListAvailableModels` 接口，查看当前支持的模型列表。

```bash
uv run python scripts/get_models.py
```

> 需要有效的 token 文件（`data/tokens/` 或 `~/.aws/sso/cache/`）。

---

### proxy_server.py — Mock API 服务器

一个模拟 Kiro API 的 FastAPI 服务器，用于测试请求拦截和格式验证，不会调用真实 API。

```bash
uv run python scripts/proxy_server.py
# 启动后访问:
#   http://127.0.0.1:8000/       — 健康检查
#   http://127.0.0.1:8000/logs   — 查看捕获的请求
#   http://127.0.0.1:8000/clear  — 清空日志
```

配合 `test_proxy.py` 使用。

---

### test_proxy.py — Mock 服务器测试

测试 `proxy_server.py` 的各个端点是否正常工作。

```bash
# 先启动 mock 服务器
uv run python scripts/proxy_server.py

# 另一个终端运行测试
uv run python scripts/test_proxy.py
```

---

### test_kiro_proxy.py — 正式代理测试

测试 KiroProxy 主程序（`run.py`）是否正常工作，包括健康检查、Token 状态、模型列表、聊天接口。

```bash
# 先启动 KiroProxy
uv run python run.py

# 另一个终端运行测试
uv run python scripts/test_kiro_proxy.py
```
