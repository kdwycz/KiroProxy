## Why

当前 429 错误的处理存在核心缺陷：冷却标记被 `rate_limiter.enabled`（默认 `False`）gate 住，导致 429 后的账号切换完全无效——两个限速账号来回切换直到重试耗尽。日志分析（766 条记录）显示 **80%+ 的 429 在 1~3 秒内自动恢复**，属于瞬时限速，但因为缺乏正确的冷却和重试机制，这些本可快速恢复的请求直接返回了 429 错误给客户端。

## What Changes

- **429 冷却独立化**：`mark_quota_exceeded()` 不再受 `rate_limiter.enabled` 控制，429 冷却始终生效
- **两阶段重试策略**：第一阶段 sleep 2~3s 后同账号重试（覆盖大多数瞬时限速）；第二阶段触发冷却+换号机制
- **指数退避冷却**：冷却时间按 `5→10→30→60→120→300s` 动态递增，成功后重置
- **已试账号追踪**：同一请求中记录已试过的账号，避免来回切换
- **智能降级**：无可用账号时等待最短冷却剩余时间，而非直接返回 429
- **Web 后台展示**：账号状态显示限速信息（冷却中/退避级别/最近 429 时间/累计 429 次数）

## Capabilities

### New Capabilities

- `exponential-backoff-cooldown`: 基于指数退避的 429 冷却机制，取代固定冷却时间，支持动态递增和成功重置
- `two-phase-retry`: 两阶段 429 重试策略——先快速重试同账号，再触发冷却+换号
- `rate-limit-dashboard`: Web 后台账号限速状态展示

### Modified Capabilities

（无现有 spec 需修改）

## Impact

- **核心模块变更**：`core/account.py`、`core/state.py`、`credential/quota.py`
- **Handler 变更**：`handlers/anthropic.py`、`handlers/openai.py`、`handlers/gemini.py` 的重试循环
- **Admin API 变更**：`handlers/admin.py` 增加限速状态字段
- **WebUI 前端变更**：账号状态卡片展示限速信息
- **无 Breaking Changes**：所有改动向后兼容
