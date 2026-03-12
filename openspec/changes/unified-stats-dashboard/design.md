## Context

KiroProxy 目前有 5 套独立的统计/日志实现：

| 系统 | 位置 | 数据 | 持久化 | 覆盖范围 |
|------|------|------|--------|---------|
| Account 字段 | `core/account.py` | request_count, error_count, last_used | ❌ | 全 handler |
| StatsManager | `core/stats.py` | 账号/模型/hourly/token | ❌ | 4 handler |
| FlowMonitor | `core/flow_monitor.py` | 完整请求/响应体 | ✅ JSONL | 仅 anthropic |
| RequestLog | `core/state.py` | 时间/路径/模型/状态码 | ❌ | 仅 anthropic |
| usage.py | `core/usage.py` | Kiro 服务端额度 | N/A | 按需查询 |

前端 7 个 tab 中，流量/监控/日志 三个 tab 展示重叠维度的数据但来源不同。

## Goals / Non-Goals

**Goals:**
- StatsManager 成为唯一的数字统计数据源
- 每个 handler 只需调用 `stats_manager.record_request()` 一次
- 统计数据按天持久化到 `data/stats.json`
- WebUI 从 7 tab 精简为 5 tab（流量+监控合并为仪表盘）
- 日志 tab 直接读磁盘日志文件，替代 shell 查看

**Non-Goals:**
- SQLite 或数据库存储（JSON 文件足够）
- 补全 FlowMonitor 到所有 handler（独立迭代）
- 费用估算或计费功能
- 改动 usage.py（Kiro 额度查询，完全独立）

## Decisions

### 1. StatsManager 作为唯一统计源

**选择**: 删除 Account 上的冗余字段，选号/展示统一读 StatsManager

**替代方案**: 保留 Account 字段但停止直接写入，通过 StatsManager 反写 → 增加复杂度无收益

**理由**: Account 字段和 StatsManager 记录完全相同的数据，删除是最简方案

### 2. 单 JSON 文件 + 按天分区

**选择**: `data/stats.json` 内含 `total` (累计) + `daily` (按天)，自动清理 30 天前

**替代方案 A**: 按天独立文件 `stats/2026-03-11.json` → 文件多，需汇总逻辑
**替代方案 B**: 单文件纯累计 → 看不到历史趋势

**理由**: 一个文件，结构简单，有历史可看

### 3. 日志 tab 读磁盘文件

**选择**: `/api/logs` 改为读 `data/logs/kiro-proxy.log`，支持按日期选择、关键词过滤、tail 模式

**替代方案**: 保留内存 RequestLog → 功能弱且覆盖不全

**理由**: 用户不需要开 shell 就能看运行日志

### 4. 流量+监控合并为仪表盘

**选择**: 统计概览 + 请求列表(FlowMonitor) + 配额冷却 + 速度测试 合并到一个 tab

**理由**: 三个 tab 展示重叠数据，合并消除不一致

## Risks / Trade-offs

- **[Risk] 选号行为微变** — 重启后 StatsManager 加载持久化数据，选号会接续之前的平衡而非从零开始 → 实际上这是更好的行为
- **[Risk] 日志文件可能很大** — loguru 按天轮转，单日文件通常 <10MB → 前端分页加载 + 限制读取行数
- **[Trade-off] FlowMonitor 仍仅覆盖 anthropic** — 本次不扩展覆盖范围，后续独立迭代
