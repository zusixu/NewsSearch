# scheduler-automation

## 关键文件

- `app/scheduler/scheduler.py` — 核心调度逻辑（批次检测、重试策略、流水线编排）
- `app/scheduler/__init__.py` — 模块导出
- `scripts/run_daily.ps1` — 日常运行脚本，自动批次检测 + 重试
- `scripts/register_task.ps1` — Windows Task Scheduler 注册/卸载脚本
- `scripts/bootstrap.ps1` — 基础启动脚本
- `tests/test_scheduler.py` — 38 个测试用例

## 决策记录

- 运行环境为 Windows 本地，使用 conda `quant` 环境。
- 自动化使用 Windows Task Scheduler，两个任务：mm-pre-market (08:30)、mm-midday (14:00)。
- 批次检测：12:00 前 → pre-market (index 0)，12:00 后 → midday (index 1)。
- 重试策略使用指数退避，默认 max_retries=2，delay=60s，backoff=2.0。
- 所有脚本需要 Administrator 权限注册 Task Scheduler，但日常运行不需要。
- 日志通过 app/logger 的 NDJSON 格式 + TimedRotatingFileHandler 每日轮转。

## 完成状态

全部 6 个 checklist 节点已完成。

## 交接要求

- 上下文快用完时，先回写当前进度、修改文件、阻塞项和下一步，再切换新的子智能体。
