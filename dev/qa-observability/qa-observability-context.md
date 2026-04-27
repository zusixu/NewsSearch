# qa-observability

## 关键文件

- `tests/` — 42 个测试文件，1644 个测试
- `app/qa/__init__.py` — qa 模块入口
- `app/qa/error_tracker.py` — 运行时错误跟踪 (ErrorTracker, ErrorSummary)
- `app/logger/__init__.py` — 结构化日志模块入口
- `app/logger/setup.py` — JSON NDJSON + console 日志初始化
- `app/logger/formatter.py` — JSON 日志格式化器
- `app/storage/database.py` — RunLogStore, PromptProfileStore, ChainScoreStore, InfoChainStore
- `app/scheduler/scheduler.py` — DailyScheduler, RetryPolicy, 批次检测
- `dev/` — 开发文档目录（计划/上下文/任务清单）

## 决策记录

- 日志采用 JSON NDJSON 格式，按日轮转，保留 30 天历史。
- 错误跟踪通过 SQLite run_logs 表实现，由 RunLogStore 写入，ErrorTracker 查询。
- 测试框架采用 pytest，无第三方依赖。
- dev 文档更新约定：每完成一步立刻更新对应 task.md，不允许在未更新文档的情况下切换子智能体。
- 调度自动化（scheduler-automation）已完成，与 qa-observability 共同保障每日运行的稳定性。

## 循环导入修复

修复了 `app/analysis/engine.py` 中的循环导入问题 — 移除了未使用的 `from app.storage import PromptProfileStore, RunLogStore` 导入。

## 当前进度

全部 7 个 checklist 节点已完成：
1. ✅ 建立最小测试结构
2. ✅ 增加归一化测试
3. ✅ 增加信息链测试
4. ✅ 增加报告生成测试
5. ✅ 统一日志格式
6. ✅ 记录运行错误与状态
7. ✅ 明确 dev 文档更新约定

## 下一步

qa-observability 阶段已全部完成。整个项目 10 个子任务中已完成 9 个（project-bootstrap, source-collection, normalization-pipeline, entity-theme-tagging, information-chain, llm-analysis, a-share-mapping, reporting-output, scheduler-automation, qa-observability），所有 10 个阶段均已完成。

## 交接要求

- 上下文快用完时，先回写当前进度、修改文件、阻塞项和下一步，再切换新的子智能体。
