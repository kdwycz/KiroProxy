## ADDED Requirements

### Requirement: 合并流量+监控为仪表盘 tab
WebUI SHALL 将「流量」和「监控」tab 合并为一个「仪表盘」tab，包含：统计概览、请求列表（FlowMonitor）、配额冷却状态、速度测试。

#### Scenario: 仪表盘统计概览
- **WHEN** 用户打开仪表盘 tab
- **THEN** 展示总请求数、错误数、错误率、可用账号数、平均延迟、token 用量，数据来源统一为 StatsManager

#### Scenario: 请求列表
- **WHEN** 用户查看仪表盘中的请求列表
- **THEN** 展示 FlowMonitor 的请求记录，支持按协议/状态过滤和内容搜索

#### Scenario: 配额冷却状态
- **WHEN** 有账号处于冷却中
- **THEN** 仪表盘展示冷却账号列表及剩余时间，支持手动恢复

### Requirement: 精简 tab 结构
WebUI SHALL 从 7 个 tab 精简为 5 个：帮助 | 仪表盘 | 账号 | 日志 | 设置。删除独立的「流量」「监控」「API」tab。

#### Scenario: Tab 导航
- **WHEN** 用户查看 WebUI
- **THEN** 只看到 5 个 tab，无冗余的数据展示入口

### Requirement: 统计数据一致性
仪表盘中所有数字统计 SHALL 来自同一个 StatsManager 实例，避免不同区域展示不同数值。

#### Scenario: 数据源统一
- **WHEN** 仪表盘显示总请求数
- **THEN** 概览区和请求列表的统计数字一致（来自同一 StatsManager）
