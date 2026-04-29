# tech-debt-mapping-report — 上下文

## 两版差异对比

| 特性 | `mapping/report.py`（旧版） | `reports/core.py`（权威版） |
|---|---|---|
| `DailyReportChainEntry.rationale` | 缺失 | 有 |
| `DailyReportChainEntry.source_urls` | 缺失 | 有（`tuple[str, ...]`） |
| `DailyReportChainEntry.chain_analysis` | 缺失 | 有（`Optional[ChainAnalysisResult]`） |
| `DailyReportChainEntry.__post_init__` | 缺失 | 有验证（rank >= 1, confidence in [0, 1]） |
| `DailyReport.risk_warnings` | 缺失 | 有（`List[RiskWarning]`） |
| `RiskWarning` | 缺失 | 有完整定义 |
| `DailyReportBuilder.build()` 签名 | `chains_with_mappings: Sequence[DailyReportChainEntry]` | `analysis_response: AnalysisResponse, mappings: Dict, ...` |
| `DailyReportHeader.__post_init__` | 缺失 | 有验证（batch 必须是 pre-market 或 midday） |
| `MarkdownReportGenerator` 风险提示渲染 | 缺失 | 有 `_render_risk_warnings()` |
| `MarkdownReportGenerator` 排名理由渲染 | 缺失 | 有 |
| `MarkdownReportGenerator` 来源链接渲染 | 缺失 | 有 |
| `JsonReportGenerator` risk_warnings 序列化 | 缺失 | 有 |
| `ReportArchiveManager` | 缺失 | 有完整归档管理器 |
| 依赖 `app/analysis/adapters/contracts` | 无 | 有（`AnalysisResponse`, `PromptProfile`） |
| 依赖 `app/chains/evidence_retention` | 无 | 有（`ChainEvidenceBundle`） |

## 调用方分析

仅 2 个文件直接依赖 `app.mapping.report`：
- `app/mapping/__init__.py` — re-export
- `tests/test_mapping_report.py` — 旧版专属测试

所有其他消费者（`app/main.py`、`demo_reports.py`、`test_save_report.py`、
`scripts/test_report_generation.py`、`tests/test_reports.py`、
`tests/test_pipeline_integration.py`、`tests/test_url_preservation.py`）
均使用 `app.reports` / `app.reports.core`。

## 兼容性风险

旧版 `DailyReportBuilder.build()` 接收 `chains_with_mappings` 参数，
新版接收 `analysis_response` + `mappings` 等参数。
这两个签名不兼容，但实际没有任何代码通过 `from app.mapping import DailyReportBuilder` 使用旧版 builder，
因此 thin re-export 不会破坏现有调用方。
