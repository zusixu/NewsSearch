# tech-debt-mapping-report

## 问题

`app/mapping/report.py` 与 `app/reports/core.py` 存在代码重复（已知问题 #1）。

旧版 `mapping/report.py`（563 行）缺少 `risk_warnings`、`rationale`、`source_urls` 等字段，
且 `mapping/__init__.py` 仍 re-export 旧版类名。权威实现在 `reports/core.py`（1174 行）。

## 修复方案

1. ~~将 `mapping/report.py` 替换为 thin re-export~~ → 使用延迟导入（`__getattr__`）避免循环依赖
2. ~~更新 `mapping/__init__.py` 中的 re-export 指向新来源~~ → 从 `__init__.py` 移除 report re-export（避免循环导入）
3. 删除 `tests/test_mapping_report.py`（旧版专属测试，`reports/core.py` 已有 `tests/test_reports.py` 覆盖）
4. 更新文档：`PROJECT_INDEX.md`、`rule.md`、`CLAUDE.md`

## 修复过程中的关键决策

### 循环导入问题

最初方案是在 `mapping/report.py` 中直接 `from app.reports.core import ...`，但触发了循环导入：
```
app.reports.core → app.mapping.schema → app.mapping.__init__ → app.mapping.report → app.reports.core
```

解决方案：
1. `mapping/report.py` 改用 `__getattr__` 延迟导入，避免模块加载时的循环依赖
2. `mapping/__init__.py` 完全移除对 `report.py` 的 re-export（实际无代码通过 `from app.mapping import DailyReport` 使用）

### 旧版测试处理

`test_mapping_report.py` 使用旧版 `DailyReportBuilder.build()` 签名（`chains_with_mappings` 参数），
不兼容新版签名（`analysis_response` + `mappings`），且新版已有完整测试覆盖（`test_reports.py`），
因此直接删除。

## 当前进度

- [x] 基线测试通过（54 passed: test_mapping_report + test_reports）
- [x] 替换 mapping/report.py 为延迟 re-export（__getattr__）
- [x] 从 mapping/__init__.py 移除 report re-export
- [x] 删除 tests/test_mapping_report.py
- [x] 全量测试回归（1805 passed，排除预存 akshare_resolver 3 failures）
- [x] 更新 PROJECT_INDEX.md（已知问题 #1 移除、模块描述更新、测试计数 53→52）
- [x] 更新 rule.md（陷阱表更新、优先修复路线 #1 标记已修复）
- [x] 更新 CLAUDE.md（已知问题 #1 移除、模块表更新、测试计数 53→52）

## 完成总结

已修复 `mapping/report.py` 与 `reports/core.py` 的代码重复问题：
- `mapping/report.py` 从 563 行重复代码精简为 30 行延迟 re-export
- `mapping/__init__.py` 不再 re-export 报告符号，消除了循环导入风险
- 删除了 650 行旧版专属测试
- 全量测试回归通过
