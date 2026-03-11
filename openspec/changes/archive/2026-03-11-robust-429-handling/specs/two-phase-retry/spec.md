## ADDED Requirements

### Requirement: Phase 1 Quick Retry

收到 429 错误后，系统 SHALL 先 sleep 2~3 秒然后用同一账号重试，不触发冷却标记。

#### Scenario: First 429 triggers quick retry
- **WHEN** 请求返回 429 且该请求尚未进行过快速重试
- **THEN** 系统 SHALL sleep 约 2 秒后用同一账号重新发送请求，不调用 `mark_quota_exceeded()`

#### Scenario: Quick retry succeeds
- **WHEN** 快速重试后请求成功（HTTP 200）
- **THEN** 系统 SHALL 正常返回响应，不产生任何冷却记录

### Requirement: Phase 2 Cooldown and Switch

快速重试失败后，系统 SHALL 触发冷却标记和账号切换策略。

#### Scenario: Quick retry fails triggers cooldown
- **WHEN** 快速重试后仍然返回 429
- **THEN** 系统 SHALL 调用 `mark_quota_exceeded()` 标记该账号进入冷却，然后执行换号策略

### Requirement: Tried Accounts Tracking

同一请求中 SHALL 追踪所有已尝试过的账号，避免重复切换。

#### Scenario: Tried accounts excluded from selection
- **WHEN** 系统在同一请求内需要切换账号
- **THEN** `get_next_available_account()` SHALL 排除所有已尝试过的账号（传入 `exclude_ids` 集合）

#### Scenario: No circular switching
- **WHEN** 有 2 个账号 A 和 B，A 收到 429 后切换到 B，B 也收到 429
- **THEN** 系统 SHALL 不再切回 A，而是执行降级策略

### Requirement: Graceful Degradation

当无可用账号时，系统 SHALL 根据最短冷却剩余时间决定等待或返回错误。

#### Scenario: Short cooldown wait
- **WHEN** 所有账号都在冷却中，最短冷却剩余时间 ≤ 5 秒
- **THEN** 系统 SHALL sleep 等待剩余时间后重试该账号

#### Scenario: Long cooldown return error
- **WHEN** 所有账号都在冷却中，最短冷却剩余时间 > 5 秒
- **THEN** 系统 SHALL 返回 429 错误给客户端

### Requirement: Max Retry Bound

重试次数 SHALL 受到上限约束。

#### Scenario: Retry count limited
- **WHEN** 同一请求的重试次数（含快速重试+换号重试）达到 `max(len(accounts), 3)` 次
- **THEN** 系统 SHALL 停止重试，返回 429 错误给客户端
