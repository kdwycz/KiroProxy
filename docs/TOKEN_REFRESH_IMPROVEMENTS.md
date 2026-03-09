# Token 刷新机制改进计划

> 基于 kiro-account-manager 项目对比分析，整理可参考的改进项。
> 创建时间：2026-03-09

## 改进项

### 1. 🔴 刷新重试机制

**现状**：`TokenRefresher.refresh()` 零重试，网络波动直接标记 UNHEALTHY。

**目标**：网络错误重试 3 次，1 秒间隔。HTTP 错误（401/429）不重试。

**改动文件**：`kiro_proxy/credential/refresher.py`

```python
async def refresh(self) -> Tuple[bool, str]:
    # ...验证 refresh_token...

    max_retries = 3
    last_error = ""
    for attempt in range(max_retries):
        if attempt > 0:
            await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                resp = await client.post(refresh_url, json=body, headers=headers)
                if resp.status_code != 200:
                    # HTTP 错误不重试，直接返回
                    return False, self._handle_http_error(resp)
                # 成功处理...
                return True, new_token
        except Exception as e:
            last_error = str(e)
            continue
    return False, f"刷新失败（{max_retries}次重试后）: {last_error}"
```

---

### 2. 🔴 原子文件写入

**现状**：`KiroCredentials.save_to_file()` 直接 `open(path, "w")` 覆盖，崩溃可能损坏文件。

**目标**：先写 `.tmp`，再 `os.rename()` 原子替换。

**改动文件**：`kiro_proxy/credential/types.py`

```python
import os

def save_to_file(self, path: str):
    existing = {}
    if Path(path).exists():
        try:
            with open(path) as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update({k: v for k, v in self.to_dict().items() if v is not None})

    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(existing, f, indent=2)
    os.rename(tmp_path, path)
```

---

### 3. 🟡 封禁检测

**现状**：健康检查只看 `/models` 返回的 HTTP 状态码，无法区分"token 过期"和"账号被封"。

**目标**：后台定期调用 `getUsageLimits` API，解析 `reason` 字段检测封禁，标记为 `SUSPENDED`。

**改动文件**：
- `kiro_proxy/core/scheduler.py` — 新增低频完整同步周期（每 30-60 分钟）
- `kiro_proxy/core/account.py` — 新增 `sync_usage()` 方法
- `kiro_proxy/credential/types.py` — `CredentialStatus.SUSPENDED` 已存在

**参考**：kiro-account-manager 的 `account_cmd.rs` `sync_account` 函数，解析 usage API 响应中的 `BANNED:` 前缀。

```python
# scheduler.py 新增
async def _sync_usage(self, state):
    """低频完整同步：刷新 + 用量 + 封禁检测"""
    for acc in state.accounts:
        if not acc.enabled:
            continue
        usage_result = await get_account_usage(acc)
        if not usage_result[0] and "BANNED" in str(usage_result[1]):
            acc.status = CredentialStatus.SUSPENDED
```

---

### 4. 🟢 真实 MachineID 支持（可选）

**现状**：`fingerprint.py` 基于凭证哈希 + 时间槽合成 MachineID。

**目标**：增加选项，可从 Kiro IDE 的 `storage.json` / `state.vscdb` 读取真实遥测 ID。

**参考**：kiro-account-manager 的 `kiro.rs` `get_kiro_telemetry_info_inner()` 函数。

读取路径：
- macOS: `~/Library/Application Support/Kiro/User/globalStorage/storage.json` → `telemetry.machineId`
- Linux: `~/.config/Kiro/User/globalStorage/storage.json`
- `state.vscdb` (SQLite): `SELECT value FROM ItemTable WHERE key = 'storage.serviceMachineId'`

---

### 5. 🟢 Provider 抽象（可选）

**现状**：`TokenRefresher` 内部 `if auth_method == "idc"` 分支处理。

**目标**：提取 `SocialRefresher` / `IdCRefresher` 子类。当前逻辑简单，优先级最低。
