## ADDED Requirements

### Requirement: 读取磁盘日志文件
日志 tab SHALL 读取 `data/logs/` 目录下的 loguru 日志文件，而非内存中的 RequestLog。

#### Scenario: 查看当天日志
- **WHEN** 用户打开日志 tab
- **THEN** 展示当天 `kiro-proxy.log` 的最新内容（tail 模式，最新在前）

#### Scenario: 选择历史日期
- **WHEN** 用户选择一个历史日期
- **THEN** 加载对应的轮转日志文件（如 `kiro-proxy.log.2026-03-10`）

### Requirement: 日志搜索过滤
系统 SHALL 支持对日志内容进行关键词搜索和级别过滤。

#### Scenario: 关键词搜索
- **WHEN** 用户输入搜索关键词（如 "429" 或 "ERROR"）
- **THEN** 只展示包含该关键词的日志行

#### Scenario: 级别过滤
- **WHEN** 用户选择日志级别（INFO/WARNING/ERROR）
- **THEN** 只展示该级别及以上的日志

### Requirement: 分页加载
系统 SHALL 分页加载日志内容，避免大文件导致前端卡顿。

#### Scenario: 初始加载
- **WHEN** 日志 tab 初次加载
- **THEN** 只加载最新的 200 行

#### Scenario: 加载更多
- **WHEN** 用户点击「加载更多」
- **THEN** 加载前 200 行旧日志并追加显示
