## ADDED Requirements

### Requirement: Exponential Backoff Levels

系统 SHALL 使用 6 级指数退避序列 `[5, 10, 30, 60, 120, 300]` 秒作为 429 冷却时间。每个账号独立维护当前退避级别。

#### Scenario: First 429 triggers level 1 cooldown
- **WHEN** 账号首次收到 429 错误（退避计数器为 0）
- **THEN** 该账号的冷却时间 SHALL 设置为 5 秒，退避级别递增为 1

#### Scenario: Consecutive 429s escalate cooldown
- **WHEN** 账号在冷却恢复后再次收到 429 错误
- **THEN** 冷却时间 SHALL 按序列递增（5→10→30→60→120→300s），退避级别 +1

#### Scenario: Cooldown caps at maximum
- **WHEN** 退避级别已达到最高级（level 5，对应 300s）
- **THEN** 后续 429 的冷却时间 SHALL 保持 300 秒不再增加

### Requirement: Successful Request Resets Backoff

成功请求 SHALL 重置账号的退避级别。

#### Scenario: Success resets to level 0
- **WHEN** 账号成功完成一次请求（HTTP 200）
- **THEN** 该账号的退避级别 SHALL 重置为 0，下次 429 将从 5 秒开始

### Requirement: Cooldown Independent of Rate Limiter

429 冷却 SHALL 独立于 `rate_limiter.enabled` 配置项，始终生效。

#### Scenario: Cooldown works when rate limiter disabled
- **WHEN** `rate_limiter.enabled` 为 `False` 且账号收到 429 错误
- **THEN** `mark_quota_exceeded()` SHALL 创建冷却记录，账号在冷却期内 `is_available()` 返回 `False`

#### Scenario: Rate limiter controls only proactive throttling
- **WHEN** `rate_limiter.enabled` 为 `False`
- **THEN** 主动限速功能（请求间隔、RPM 限制）SHALL 保持关闭，仅 429 冷却生效
