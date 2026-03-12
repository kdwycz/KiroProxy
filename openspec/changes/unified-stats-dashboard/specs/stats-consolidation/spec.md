## ADDED Requirements

### Requirement: StatsManager 为唯一统计数据源
系统 SHALL 使用 `StatsManager` 作为所有请求统计的唯一数据源。Account 上 SHALL NOT 存在独立的 `request_count`、`error_count`、`last_used` 字段。

#### Scenario: Handler 记录请求
- **WHEN** 任意 handler 处理完一个请求（成功或失败）
- **THEN** 只调用 `stats_manager.record_request()` 一次，不直接修改 Account 字段

#### Scenario: 选号读取统计
- **WHEN** `get_available_account()` 执行选号
- **THEN** 通过 `stats_manager.by_account[id].total_requests` 获取请求计数

#### Scenario: 状态展示
- **WHEN** `get_status_info()` 返回账号状态
- **THEN** `request_count`、`error_count` 从 StatsManager 读取

### Requirement: 统计数据按天持久化
系统 SHALL 将统计数据持久化到 `data/stats.json`，包含累计总量和按天分区。

#### Scenario: 定时保存
- **WHEN** 距上次保存已过 60 秒
- **THEN** 系统自动将当前统计写入 `data/stats.json`

#### Scenario: 启动加载
- **WHEN** 服务启动且 `data/stats.json` 存在
- **THEN** 加载历史统计数据，选号计数接续

#### Scenario: 按天分区
- **WHEN** 统计数据写入
- **THEN** `daily` 字段按日期 key 存储当天汇总，自动清理 30 天前的记录

### Requirement: 删除 RequestLog
系统 SHALL 删除 `state.RequestLog` 数据类、`request_logs` deque、`add_log()` 方法。`state.get_stats()` SHALL 代理 StatsManager 提供数据。

#### Scenario: 统计接口兼容
- **WHEN** 前端调用 `/api/stats`
- **THEN** 返回的 JSON 字段名与现有格式兼容（total_requests、total_errors、error_rate 等）
