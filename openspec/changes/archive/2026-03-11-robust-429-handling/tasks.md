## 1. 指数退避冷却基础设施

- [x] 1.1 改造 `QuotaRecord` 数据类，增加 `backoff_level`（int）、`last_429_at`（float）、`total_429_count`（int）字段
- [x] 1.2 在 `QuotaManager` 中实现 `BACKOFF_SEQUENCE = [5, 10, 30, 60, 120, 300]`，`mark_exceeded()` 方法根据当前 `backoff_level` 选择冷却时间并递增级别
- [x] 1.3 在 `QuotaManager` 中增加 `reset_backoff(credential_id)` 方法，成功请求时调用重置退避级别
- [x] 1.4 在 `QuotaManager` 中增加 `get_rate_limit_info(credential_id)` 方法，返回 `is_cooldown`、`cooldown_remaining`、`backoff_level`、`last_429_at`、`total_429_count`

## 2. 429 冷却独立化

- [x] 2.1 修改 `Account.mark_quota_exceeded()`：移除 `rate_limiter.should_apply_quota_cooldown()` 检查，始终调用 `quota_manager.mark_exceeded()` 并传入退避时间
- [x] 2.2 修改 `Account` 增加 `reset_quota_backoff()` 方法，在成功请求后调用 `quota_manager.reset_backoff()`

## 3. 两阶段重试 + 换号策略

- [x] 3.1 修改 `ProxyState.get_next_available_account()` 支持 `exclude_ids: Set[str]` 参数
- [x] 3.2 在 `ProxyState` 中增加 `get_shortest_cooldown()` 方法，返回所有冷却账号中最短的剩余冷却时间和对应账号
- [x] 3.3 改造 `handlers/anthropic.py` 的 `_handle_non_stream` 重试循环：实现两阶段重试（快速重试 → 冷却+换号），追踪 `tried_accounts` 集合
- [x] 3.4 改造 `handlers/anthropic.py` 的 `_handle_stream` 重试循环：同上逻辑
- [x] 3.5 改造 `handlers/openai.py` 的重试循环：同上逻辑
- [x] 3.6 改造 `handlers/gemini.py` 的重试循环：同上逻辑
- [x] 3.7 在所有 handler 的成功路径中调用 `current_account.reset_quota_backoff()` 重置退避

## 4. Web 后台展示

- [x] 4.1 修改 `Account.get_status_info()` 返回限速相关字段（`rate_limit` 对象）
- [x] 4.2 修改 `handlers/admin.py` 的 `get_account_detail()` 返回限速详情
- [x] 4.3 更新 WebUI 前端账号状态卡片展示限速信息（冷却状态/退避级别/剩余时间）

## 5. 验证

- [x] 5.1 手动测试：启动代理，发送请求直到触发 429，验证快速重试 → 冷却 → 换号的完整流程
- [ ] 5.2 通过 WebUI 验证账号限速状态展示正确
- [ ] 5.3 验证 API 接口 `GET /api/accounts` 返回 `rate_limit` 字段
