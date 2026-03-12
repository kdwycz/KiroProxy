## Why

系统中存在 5 套独立的统计/日志实现（Account 字段、StatsManager、FlowMonitor、RequestLog、usage.py），数据高度重叠，每个 handler 需要同时调用多套系统记录同一个请求。前端也有对应冗余：流量 tab、监控 tab、日志 tab 展示相同维度的数据但来源不同，数值可能不一致。

## What Changes

- **删除** `Account.request_count`、`error_count`、`last_used` — 被 StatsManager 完全覆盖
- **删除** `state.RequestLog`、`request_logs` deque、`add_log()` — 半成品，仅 anthropic 使用
- **改造** StatsManager 为唯一统计源，加按天持久化（`data/stats.json`）
- **改造** 选号逻辑读 StatsManager 而非 Account.request_count
- **合并** WebUI 流量+监控 tab 为「仪表盘」tab
- **改造** WebUI 日志 tab 为磁盘日志文件查看器（读 `data/logs/kiro-proxy.log`）
- **删除** WebUI API tab（合并到帮助 tab 或删除）
- **精简** WebUI 从 7 tab 到 5 tab：帮助 | 仪表盘 | 账号 | 日志 | 设置

## Capabilities

### New Capabilities
- `stats-consolidation`: 合并 5 套统计为 StatsManager 单一数据源，加按天持久化
- `unified-dashboard`: 合并流量+监控 tab 为仪表盘，统一数据展示
- `log-viewer`: 日志 tab 改为磁盘日志文件查看器，支持搜索/过滤/选择日期

### Modified Capabilities
_(无已有 spec)_

## Impact

- **后端**: `core/stats.py`、`core/account.py`、`core/state.py`、5 个 handler 文件、`handlers/admin.py`
- **前端**: `web/webui.py` 大幅改造（tab 合并、日志查看器）
- **API**: `/api/logs` 改为读磁盘文件；`/api/stats` 数据源变更（接口字段兼容）
- **持久化**: 新增 `data/stats.json` 文件
