## 1. StatsManager 改造 + 持久化

- [x] 1.1 StatsManager 加 `total_requests`/`total_errors` 全局计数器
- [x] 1.2 StatsManager 加按天分区：`daily: Dict[str, DailyStats]`，record 时同时更新 daily
- [x] 1.3 实现 `save()` — 写入 `data/stats.json`（total + daily，清理 30 天前）
- [x] 1.4 实现 `load()` — 启动时加载历史数据
- [x] 1.5 实现自动保存：每 60 秒或进程退出时调用 `save()`

## 2. 删除冗余统计字段

- [x] 2.1 删除 `Account.request_count`、`error_count`、`last_used` 字段
- [x] 2.2 改造 `Account.get_status_info()` 从 StatsManager 读取统计
- [x] 2.3 改造 `state.get_available_account()` 选号读 `stats_manager.by_account[id].total_requests`
- [x] 2.4 删除 `state.RequestLog` 数据类、`request_logs` deque、`add_log()` 方法
- [x] 2.5 改造 `state.get_stats()` 代理 StatsManager 数据

## 3. Handler 清理

- [x] 3.1 删除所有 handler 中的 `account.request_count += 1` 行
- [x] 3.2 删除所有 handler 中的 `account.error_count += 1` 行
- [x] 3.3 删除 anthropic handler 中的 `state.add_log()` 调用
- [x] 3.4 确保每个 handler 的成功/失败路径都有且只有一次 `stats_manager.record_request()` 调用

## 4. Admin API 适配

- [x] 4.1 改造 `/api/logs` 为磁盘日志文件读取（读 `data/logs/kiro-proxy.log`）
- [x] 4.2 新增 `/api/logs/dates` — 返回可用的日志日期列表
- [x] 4.3 确保 `/api/stats` 返回格式兼容（字段名不变）
- [x] 4.4 删除 API tab 相关的无用端点（如有）

## 5. WebUI 前端改造

- [x] 5.1 合并流量+监控 tab 为「仪表盘」tab（统计概览 + 请求列表 + 配额冷却 + 速度测试）
- [x] 5.2 改造日志 tab 为磁盘日志查看器（日期选择、搜索过滤、分页加载）
- [x] 5.3 删除独立的「流量」「监控」「API」tab
- [x] 5.4 更新 tab 导航：帮助 | 仪表盘 | 账号 | 日志 | 设置

## 6. 验证

- [x] 6.1 语法检查所有修改文件
- [ ] 6.2 启动代理验证仪表盘数据展示正确
- [ ] 6.3 验证日志 tab 可读取磁盘日志、搜索过滤正常
- [ ] 6.4 验证统计持久化：重启后数据恢复
- [ ] 6.5 验证选号行为正常
