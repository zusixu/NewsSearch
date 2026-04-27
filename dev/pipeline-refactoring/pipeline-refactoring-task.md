# pipeline-refactoring task tracking

## Phase 1: 采集层简化

- [x] `config.yaml` — copilot_research: false
- [x] `app/collectors/copilot_research_collector.py` — is_enabled() 读取 sources_config
- [x] `app/main.py` — _create_collectors() 按配置决定

## Phase 2: URL 溯源透传

- [x] `app/chains/evidence_retention.py` — ChainEvidenceBundle 新增 source_urls
- [x] `app/mapping/schema.py` — DailyReportChainEntry 新增 source_urls (注: DailyReportChainEntry 实际位于 app/reports/core.py)
- [x] `app/reports/core.py` — Markdown 增加来源链接区域；JSON 增加 source_urls

## Phase 3: ReAct 多步分析引擎

- [x] `app/analysis/adapters/contracts.py` — 新增 GROUPER/REACT_STEP/REACT_FINALIZE task types
- [x] `app/analysis/prompts/templates/grouper.json` — 分组策略模板
- [x] `app/analysis/prompts/templates/react_step.json` — ReAct 单步模板
- [x] `app/analysis/prompts/templates/react_finalize.json` — ReAct finalize 模板
- [x] `app/analysis/react/__init__.py` — 公共 API
- [x] `app/analysis/react/tools.py` — Tool/ToolRegistry
- [x] `app/analysis/react/session.py` — ReActStep/ReActSession
- [x] `app/analysis/react/prompts.py` — Prompt 常量与构建
- [x] `app/analysis/react/engine.py` — ReActAnalysisEngine
- [x] `app/analysis/engine.py` — 整合 ReActAnalysisEngine + mode 切换
- [x] `app/analysis/__init__.py` — 导出 react 模块

## Phase 4: 配置与模式开关

- [x] `app/config/schema.py` — 新增 AnalysisConfig
- [x] `app/config/loader.py` — 新增 _build_analysis()
- [x] `config.yaml` — 新增 analysis 配置节
- [x] `app/main.py` — CLI --analysis-mode {react,legacy}

## Phase 5: 测试

- [x] `tests/test_collector_optional.py` — 8 tests: is_enabled() contract + _create_collectors() integration
- [x] `tests/test_url_preservation.py` — 17 tests: ChainEvidenceBundle source_urls, DailyReportChainEntry, Markdown/JSON rendering, DailyReportBuilder wiring
- [x] `tests/test_react_tools.py` — 39 tests: Tool dataclass, ToolRegistry CRUD/execute/schema, web_search/web_fetch/akshare_query stubs, default registry
- [x] `tests/test_react_session.py` — 23 tests: ReActStep fields, ReActSession init/add_step/is_finished/last_step/to_history_json
- [x] `tests/test_react_engine.py` — 45 tests: ReActEngineConfig, _strip_code_fences, _empty_analysis_response, _dry_run_grouper/session/finalize, _rank_groups, tool registry construction, run() dry-run integration
- [x] Fix tests/test_copilot_research_collector.py — updated is_enabled tests to respect sources_config (split into 3 tests)
- [x] Fix tests/test_collector_interface.py — updated test_copilot_research_always_enabled → two separate tests

Phase 5 test results: 1851 total tests (1848 passed, 3 pre-existing failures in test_akshare_resolver.py unrelated to this phase). 132 new tests added.
