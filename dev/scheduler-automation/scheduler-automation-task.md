# scheduler-automation

> 执行纪律：每完成一步，立刻更新本清单；如有阻塞，也要立刻写明当前状态与阻塞原因。

- [x] 建立日常运行脚本
- [x] 建立计划任务注册脚本
- [x] 支持补跑参数
- [x] 支持日志落盘
- [x] 设计失败重试
- [x] 编写使用说明

## 完成总结

已完成 scheduler-automation 模块的全部功能：

1. **日常运行脚本** — `scripts/run_daily.ps1`，自动检测批次（pre-market / midday），支持 conda quant 环境启动
2. **计划任务注册脚本** — `scripts/register_task.ps1`，注册两个 Windows Task Scheduler 任务（mm-pre-market 08:30、mm-midday 14:00），支持 `-Unregister` 卸载
3. **补跑参数** — `--Date YYYY-MM-DD`，在 `run_daily.ps1` 和 `bootstrap.ps1` 中均已支持
4. **日志落盘** — 通过 `app/logger` 的 JSON NDJSON 日志 + 每日轮转，`run_daily.ps1` 输出带时间戳的控制台日志
5. **失败重试** — `DailyScheduler` + `RetryPolicy`，支持可配置的最大重试次数、基础延迟、指数退避
6. **使用说明** — `bootstrap.ps1` 已有完整 `.SYNOPSIS` / `.EXAMPLE`，`run_daily.ps1` 和 `register_task.ps1` 同样具备

## 测试状态

- `tests/test_scheduler.py`：**38/38** 通过
- 全量回归：**1614/1614** 通过

## 关键文件

- `app/scheduler/scheduler.py` — 核心调度逻辑（批次检测、重试策略、流水线编排）
- `app/scheduler/__init__.py` — 模块导出
- `scripts/run_daily.ps1` — 日常运行脚本
- `scripts/register_task.ps1` — Task Scheduler 注册脚本
- `scripts/bootstrap.ps1` — 基础启动脚本（已有）
