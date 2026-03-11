## ADDED Requirements

### Requirement: Account Rate Limit Status Display

Web 后台的账号状态信息 SHALL 包含限速相关字段。

#### Scenario: Account in cooldown shows status
- **WHEN** 用户在 Web 后台查看账号列表
- **THEN** 冷却中的账号 SHALL 显示：冷却剩余秒数、当前退避级别、最近一次 429 时间

#### Scenario: Account with 429 history shows stats
- **WHEN** 用户查看账号详情
- **THEN** SHALL 显示该账号的累计 429 次数和当前退避级别

### Requirement: Rate Limit Info in API Response

Admin API 的账号状态接口 SHALL 返回限速相关字段。

#### Scenario: Account list API includes rate limit info
- **WHEN** 调用 `GET /api/accounts` 或 `GET /api/accounts/{id}`
- **THEN** 响应 SHALL 包含 `rate_limit` 对象，含字段：`is_cooldown`（bool）、`cooldown_remaining`（int/秒）、`backoff_level`（int）、`last_429_at`（float/timestamp）、`total_429_count`（int）
