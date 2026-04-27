# qa-observability

> 执行纪律：每完成一步，立刻更新本清单；如有阻塞，也要立刻写明当前状态与阻塞原因。

- [x] 建立最小测试结构
- [x] 增加归一化测试
- [x] 增加信息链测试
- [x] 增加报告生成测试
- [x] 统一日志格式
- [x] 记录运行错误与状态
- [x] 明确 dev 文档更新约定

## 完成总结

所有 7 个 checklist 节点均已完成：

1. **最小测试结构** — `tests/` 目录下 42 个测试文件，1644 个测试全部通过
2. **归一化测试** — test_raw_document (11), test_news_item (29), test_event_draft (37), test_url_dedup (48), test_text_dedup (51), test_time_norm (87), test_source_credibility (80) — 合计 343 个测试
3. **信息链测试** — test_chain (39), test_relation_type (40), test_same_topic_grouping (36), test_temporal_connection (36), test_upstream_downstream (48), test_candidate_generation (35), test_evidence_retention (41) — 合计 275 个测试
4. **报告生成测试** — test_reports (32 个测试)
5. **统一日志格式** — `app/logger/` 模块，JSON NDJSON 文件日志 + 控制台输出，按日轮转
6. **记录运行错误与状态** — `ErrorTracker` (app/qa/error_tracker.py) + `RunLogStore` (app/storage/database.py) + test_error_tracker.py (15 个测试) + test_scheduler.py (38 个测试) + test_pipeline_integration.py (16 个测试)
7. **dev 文档更新约定** — 已写入 CLAUDE.md 和 plan.md，每完成一步立刻更新对应任务清单

## 测试状态

- `tests/test_error_tracker.py`：**15/15** 通过
- `tests/test_pipeline_integration.py`：**16/16** 通过
- `tests/test_scheduler.py`：**38/38** 通过
- 全量回归：**1644/1644** 通过

## 关键文件

- `app/qa/__init__.py` — qa 模块入口，导出 ErrorTracker / ErrorSummary
- `app/qa/error_tracker.py` — 运行时错误跟踪与查询
- `app/logger/__init__.py` — 结构化日志模块入口
- `app/logger/setup.py` — 日志初始化（JSON NDJSON + 控制台）
- `app/logger/formatter.py` — JSON 格式化器
- `app/storage/database.py` — RunLogStore / PromptProfileStore / ChainScoreStore / InfoChainStore
- `app/scheduler/scheduler.py` — DailyScheduler / RetryPolicy / 批次检测

## 循环导入修复

修复了 `app/analysis/engine.py` 中的循环导入问题：移除了未使用的 `from app.storage import PromptProfileStore, RunLogStore` 导入。

循环导入链：`app.storage.database` → `app.analysis` → `app.analysis.engine` → `app.storage`
