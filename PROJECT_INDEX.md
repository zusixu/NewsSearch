# MM 项目索引 — AI 开发助手速查手册

> 本文件供后续 AI 修改/优化代码时快速定位使用。与 `CLAUDE.md`（运行指南与约定）和 `rule.md`（开发规范）互补，侧重**代码级结构索引**。

---

## 1. 项目概览

**mm** — Daily AI Investment News Pipeline。每日自动采集 AI/科技投资新闻，经归一化、实体标注、信息链构建、LLM 分析、A 股映射后，输出结构化日报（Markdown + JSON）。

**架构分层**：
```
collect → normalize → entity/theme tagging → information chain → llm analysis → a-share mapping → ranking → reporting
```

**LLM 分析支持双模式**：
- `legacy`（默认）：单次 LLM 调用完成分析+排序
- `react`：多步 ReAct 智能体 — Grouper 分组 → 逐组 ReAct 迭代（可调工具） → Finalize → 跨组排序

切换方式：`config.yaml` 中 `analysis.mode` 或 CLI `--analysis-mode {react,legacy}`

**环境约束**：
- Windows 10/11，PowerShell 5.1+
- Conda `quant` 环境（Python 3.11），AkShare 已预装
- SQLite: `data/db/mm.db`

---

## 2. 目录结构索引

```text
mm/
├── app/                          # 主代码
│   ├── main.py                   # CLI 入口 (667 行) — run / dry-run / collect-only / analyze-only
│   ├── config/                   # 配置加载 (838 行)
│   │   ├── loader.py             # .env + YAML 加载 (306 行)
│   │   ├── schema.py             # 配置类型定义 (176 行)
│   │   └── override.py           # 配置覆盖层 (286 行)
│   ├── collectors/               # 采集层 (2560 行)
│   │   ├── base.py               # Collector Protocol / 统一接口 (251 行)
│   │   ├── akshare_collector.py  # AkShare 适配器 — CCTV + Caixin (305 行)
│   │   ├── web_collector.py      # RSS/Atom + 静态 HTML (492 行)
│   │   ├── copilot_research_collector.py  # web-access 研究采集器 (364 行)
│   │   ├── web_access_transport.py # CDP proxy + 多后端搜索 + 直接源抓取 (805 行)
│   │   ├── collection_cache.py   # 文件系统缓存 (184 行)
│   │   └── retry.py              # 通用重试策略 (107 行)
│   ├── models/                   # 跨层共享数据模型 (353 行)
│   │   ├── raw_document.py       # RawDocument (78 行)
│   │   ├── news_item.py          # NewsItem (120 行)
│   │   └── event_draft.py        # EventDraft (127 行)
│   ├── normalize/                # 归一化层 (~1315 行)
│   │   ├── url_dedup.py          # URL 指纹去重 (163 行)
│   │   ├── text_dedup.py         # title+body SHA-256 去重 (184 行)
│   │   ├── time_norm.py          # 多格式时间标准化 (323 行)
│   │   ├── source_credibility.py # 来源可信度分级 0–5 (376 行)
│   │   ├── _item_merge.py        # 归一化合并辅助 (83 行)
│   │   └── date_filter.py        # 日期过滤 (113 行)
│   ├── entity/                   # 实体与主题标注 (~1157 行)
│   │   ├── themes.py             # 11 个 ThemeId + THEME_TAXONOMY (229 行)
│   │   ├── entity_types.py       # 6 种 EntityType + ENTITY_TYPE_TAXONOMY (188 行)
│   │   ├── rules/extractor.py    # 确定性规则抽取 (CJK+ASCII 双路径) (182 行)
│   │   ├── model_extractor.py    # 模型补充抽取 Protocol (157 行)
│   │   ├── evidence.py           # EvidenceSpan / EvidenceLink (194 行)
│   │   └── tagged_output.py      # TaggedOutput 输出层 (129 行)
│   ├── chains/                   # 信息链构建层 (~1034 行)
│   │   ├── chain.py              # ChainNode / InformationChain / build_chain (166 行)
│   │   ├── relation_type.py      # RelationType 枚举 — 4 种 (42 行)
│   │   ├── same_topic_grouping.py# 同主题传递闭包 (Union-Find) (191 行)
│   │   ├── temporal_connection.py# 时序重排 + TEMPORAL 标记 (135 行)
│   │   ├── upstream_downstream.py# 上下游保守阶段映射 (218 行)
│   │   ├── candidate_generation.py# 候选链流水线 (87 行)
│   │   └── evidence_retention.py # 链证据聚合 (167 行)
│   ├── analysis/                 # LLM 分析层 (~2928 行)
│   │   ├── adapters/
│   │   │   ├── contracts.py      # AnalysisAdapter Protocol + PromptTaskType (6种) (353 行)
│   │   │   ├── github_models.py  # GitHubModelsAdapter (404 行)
│   │   │   └── openai_compatible.py # OpenAI 兼容适配器 (336 行)
│   │   ├── prompts/
│   │   │   ├── file_system_renderer.py  # 模板加载器 (253 行)
│   │   │   ├── profile.py        # PromptProfile 读取解析 (357 行)
│   │   │   └── templates/        # 6 个 JSON prompt 模板
│   │   ├── react/                # ReAct 多步分析引擎
│   │   │   ├── tools.py          # Tool / ToolRegistry + 3 工具 (222 行)
│   │   │   ├── session.py        # ReActStep / ReActSession 状态机 (124 行)
│   │   │   ├── prompts.py        # GrouperContext / ReActContext (189 行)
│   │   │   └── engine.py         # ReActAnalysisEngine (683 行)
│   │   └── engine.py             # AnalysisEngine（legacy/react 双模式）(438 行)
│   ├── mapping/                  # A 股映射层
│   │   ├── schema.py             # AShareMapping / MappingLevel 等 9 个 dataclass (515 行)
│   │   ├── industry_chain.py     # AI 产业链 11 个环节映射 (432 行)
│   │   ├── engine.py             # 映射引擎 + 评分引擎 + 证据采集 (1047 行)
│   │   ├── report.py             # ⚠️ 旧版日报辅助 (563 行) — 与 reports/core.py 重复
│   │   └── akshare_resolver.py   # AkShare 股票代码动态解析
│   ├── reports/                  # 报告输出层
│   │   └── core.py               # DailyReport / MarkdownReportGenerator / JsonReportGenerator / ReportArchiveManager (1174 行)
│   ├── scheduler/                # 调度层
│   │   └── scheduler.py          # DailyScheduler / RetryPolicy / determine_batch (321 行)
│   ├── qa/                       # 质量与可观测性
│   │   └── error_tracker.py      # ErrorTracker / ErrorSummary (181 行)
│   ├── logger/                   # 日志 (~189 行)
│   │   ├── setup.py              # JSON NDJSON + 控制台 (81 行)
│   │   └── formatter.py          # 日志格式器 (72 行)
│   ├── storage/                  # 存储层 (~1019 行)
│   │   ├── database.py           # SQLite 连接 + Store 类 (773 行)
│   │   └── schema.sql            # 数据库 DDL — 9 张表 (206 行)
│   └── ranking/                  # ⚠️ 占位模块 — 空文件，排序逻辑在 analysis/engine.py
│       └── __init__.py           # (0 行)
├── tests/                        # 测试集 (53 个 pytest 文件)
├── scripts/                      # PowerShell 脚本
│   ├── bootstrap.ps1             # 主启动脚本 (推荐入口)
│   ├── run_daily.ps1             # 日常运行脚本
│   └── register_task.ps1         # Windows Task Scheduler 注册/卸载
├── dev/                          # 开发任务文档 (14 子目录, 42 个 md 文件)
├── config/                       # 配置文件
│   ├── prompt_profiles/default.yaml
│   └── override.example.yaml
├── data/                         # 数据目录
│   ├── db/mm.db                  # SQLite 主库
│   ├── raw/akshare/              # 采集缓存
│   └── reports/YYYY/MM/DD/       # 日报归档
├── config.yaml                   # 业务配置
├── PROJECT_INDEX.md              # 本文件 — 代码级结构索引
├── CLAUDE.md                     # 运行指南与约定
└── rule.md                       # 开发规范文档
```

---

## 3. 数据流契约（端到端）

```
RawDocument     (app/models/raw_document.py)
    ↓  normalize
NewsItem        (app/models/news_item.py)
    ↓  entity/theme tagging
EventDraft + TaggedOutput   (app/models/event_draft.py + app/entity/tagged_output.py)
    ↓  chain building
InformationChain + ChainEvidenceBundle   (app/chains/chain.py + evidence_retention.py)
    ↓  llm analysis (legacy: 单次调用 / react: Grouper→ReAct loop→Finalize→Ranking)
AnalysisResponse + ChainScores   (app/analysis/adapters/contracts.py + app/storage/database.py)
    ↓  a-share mapping
AShareMapping + MappingScore   (app/mapping/schema.py + engine.py)
    ↓  reporting
DailyReport     (app/reports/core.py)
    ↓  archive
Markdown + JSON → data/reports/YYYY/MM/DD/YYYYMMDD-{pre-market|midday}.{md|json}
```

**关键跨层引用字段**：
- `RawDocument.id` → `NewsItem.raw_document_id`（通过 `raw_refs` 列表追溯）
- `NewsItem.id` → `EventDraft.source_items`（隐含）
- `RunLog.id` → `RawDocument.run_id`, `NewsItem.run_id`, `InfoChain.run_id`
- `ChainScore.chain_id` → `InfoChain.id`

---

## 4. 模块速查表

| 模块 | 关键文件 | 核心类/函数 | 职责 |
|---|---|---|---|
| **CLI 入口** | `app/main.py` | `main()`, `run()`, `dry_run()`, `collect_only()`, `analyze_only()` | 参数解析、模式分发、pipeline 编排 |
| **配置** | `app/config/schema.py` | `AppConfig`, `SourcesConfig`, `AnalysisConfig`, `LLMConfig` | 配置类型定义 |
| | `app/config/loader.py` | `load_config()`, `load_env()` | 加载 `.env` + `config.yaml` |
| | `app/config/override.py` | `load_override()`, `apply_override()` | 运行时覆盖配置 |
| **采集** | `app/collectors/base.py` | `BaseCollector` (ABC), `RunContext`, `CollectResult` | 统一采集接口 |
| | `app/collectors/akshare_collector.py` | `AkShareCollector` | CCTV、Caixin 等财经新闻（懒加载 akshare） |
| | `app/collectors/web_collector.py` | `WebCollector` | RSS/Atom/静态 HTML（纯 stdlib） |
| | `app/collectors/copilot_research_collector.py` | `CopilotResearchCollector`, `ResearchTransport` | web-access 研究采集器 |
| | `app/collectors/web_access_transport.py` | `WebAccessTransport`, `CDPProxyClient` | CDP proxy + 多后端搜索 + 直接源抓取 |
| **归一化** | `app/normalize/url_dedup.py` | `canonicalize_url()`, `deduplicate_by_url()` | URL 规范化去重 |
| | `app/normalize/text_dedup.py` | `text_fingerprint()`, `deduplicate_by_text()` | 文本 SHA-256 去重 |
| | `app/normalize/time_norm.py` | `normalize_time()`, `normalize_item_time()` | 多格式时间标准化 |
| | `app/normalize/source_credibility.py` | `grade_credibility()` | 8 规则 0–5 分来源可信度 |
| | `app/normalize/date_filter.py` | `filter_by_date_range()`, `filter_last_n_days()` | 日期范围过滤 |
| **实体标注** | `app/entity/themes.py` | `ThemeId`, `THEME_TAXONOMY` | 11 个主题标签体系 |
| | `app/entity/entity_types.py` | `EntityType`, `ENTITY_TYPE_TAXONOMY` | 6 种实体类型体系 |
| | `app/entity/rules/extractor.py` | `RuleExtractor`, `Hit` | 确定性规则抽取（CJK+ASCII 双路径） |
| | `app/entity/model_extractor.py` | `ModelExtractor` (Protocol) | 模型补充抽取接口（无具体实现，by design） |
| | `app/entity/tagged_output.py` | `TaggedOutput`, `build_tagged_output()` | 标签化结果输出 |
| **信息链** | `app/chains/chain.py` | `ChainNode`, `InformationChain`, `build_chain()` | 链数据结构（frozen dataclass） |
| | `app/chains/relation_type.py` | `RelationType` | 4 种关系枚举（因果/时序/上下游/同主题） |
| | `app/chains/candidate_generation.py` | `generate_candidate_chains()` | 流水线：同主题→时序→上下游 |
| | `app/chains/evidence_retention.py` | `ChainEvidenceBundle`, `collect_chain_evidence()` | 证据聚合 |
| **LLM 分析** | `app/analysis/adapters/contracts.py` | `AnalysisAdapter`, `AnalysisInput`, `AnalysisResponse`, `PromptTaskType` | 适配器契约 + 6 种任务类型 |
| | `app/analysis/adapters/github_models.py` | `GitHubModelsAdapter`, `ChatMessage`, `PromptRenderer` | GitHub Models 调用实现 |
| | `app/analysis/adapters/openai_compatible.py` | `OpenAICompatibleAdapter` | OpenAI 兼容端点调用（含 code-fence 剥离） |
| | `app/analysis/engine.py` | `AnalysisEngine`, `DryRunAnalysisAdapter` | 分析引擎（legacy/react 双模式） |
| | `app/analysis/react/engine.py` | `ReActAnalysisEngine`, `ReActEngineConfig` | ReAct 多步分析：Grouper→ReAct loop→Finalize→Ranking |
| | `app/analysis/react/tools.py` | `Tool`, `ToolRegistry`, 3 个工具实例 | ReAct 工具定义与注册（2 个 stub） |
| | `app/analysis/react/session.py` | `ReActStep`, `ReActSession` | ReAct 单步/会话状态机 |
| | `app/analysis/react/prompts.py` | `GrouperContext`, `ReActContext` | ReAct prompt 上下文构建 |
| | `app/analysis/prompts/profile.py` | `PromptProfile`, `load_prompt_profile()` | prompt profile 读取 |
| **A 股映射** | `app/mapping/schema.py` | `AShareMapping`, `MappingScore`, `MappingEvidence` 等 9 个 dataclass | 映射数据结构 |
| | `app/mapping/industry_chain.py` | `IndustryChainMap`, 11 个 `IndustryChainNode` | AI 产业链映射关系（硬编码） |
| | `app/mapping/engine.py` | `AShareMappingEngine`, `MappingScoringEngine`, `MappingEvidenceCollector` | 映射转换 + 5 维度评分 + 证据采集 |
| | `app/mapping/report.py` | ⚠️ 旧版日报辅助（与 `reports/core.py` 重复） | — |
| **报告** | `app/reports/core.py` | `DailyReport`, `DailyReportBuilder`, `MarkdownReportGenerator`, `JsonReportGenerator`, `ReportArchiveManager` | 日报生成与归档（权威版本） |
| **调度** | `app/scheduler/scheduler.py` | `DailyScheduler`, `RetryPolicy`, `determine_batch()` | 每日两次调度 (08:30 + 14:00) |
| **QA** | `app/qa/error_tracker.py` | `ErrorTracker`, `ErrorSummary` | 错误跟踪与汇总 |
| **存储** | `app/storage/database.py` | `RunLogStore`, `PromptProfileStore`, `ChainScoreStore`, `InfoChainStore` | SQLite CRUD 封装 |
| **日志** | `app/logger/setup.py` | `setup_logging()` | JSON NDJSON + 控制台 |

---

## 5. 测试矩阵

| 被测模块 | 测试文件 | 覆盖范围 |
|---|---|---|
| `app/config/` | `test_config.py`, `test_override.py` | 加载、验证、覆盖 |
| `app/collectors/` | `test_collector_interface.py`, `test_akshare_collector.py`, `test_web_collector.py`, `test_copilot_research_collector.py`, `test_collection_cache.py`, `test_retry.py`, `test_collector_optional.py` | 接口、适配器、缓存、重试 |
| `app/models/` | `test_raw_document.py`, `test_news_item.py`, `test_event_draft.py` | 数据模型构建与 from_raw |
| `app/normalize/` | `test_url_dedup.py`, `test_text_dedup.py`, `test_time_norm.py`, `test_source_credibility.py`, `test_date_filter.py` | 去重、时间标准化、可信度、过滤 |
| `app/entity/` | `test_theme_taxonomy.py`, `test_entity_types.py`, `test_rule_extractor.py`, `test_model_extractor.py`, `test_evidence.py`, `test_tagged_output.py` | 标签体系、规则抽取、证据链 |
| `app/chains/` | `test_chain.py`, `test_relation_type.py`, `test_same_topic_grouping.py`, `test_temporal_connection.py`, `test_upstream_downstream.py`, `test_candidate_generation.py`, `test_evidence_retention.py` | 链构建、关系、流水线 |
| `app/analysis/` | `test_analysis_adapter_contracts.py`, `test_github_models_adapter.py`, `test_filesystem_prompt_renderer.py`, `test_prompt_profile.py`, `test_prompt_version_tracking.py`, `test_analysis_engine.py` | 适配器、渲染器、profile |
| `app/analysis/react/` | `test_react_tools.py`, `test_react_session.py`, `test_react_engine.py` | 工具、会话、引擎 |
| `app/mapping/` | `test_a_share_mapping_schema.py`, `test_industry_chain.py`, `test_mapping_engine.py`, `test_mapping_score.py`, `test_mapping_evidence.py`, `test_mapping_report.py` | 映射、评分、证据 |
| `app/reports/` | `test_reports.py` | 日报生成与归档 |
| `app/scheduler/` | `test_scheduler.py` | 调度与重试 |
| `app/qa/` | `test_error_tracker.py`, `test_pipeline_integration.py` | 错误跟踪、集成测试 |
| URL 溯源 | `test_url_preservation.py` | URL 传递链 |
| `app/storage/` | `test_storage.py` | Schema、连接、CRUD |
| `app/logger/` | `test_logger.py` | JSON 格式、handler 设置 |

**全量回归命令**：`pytest tests/ -q`（53 个测试文件）

---

## 6. 配置与存储索引

### 配置文件

| 文件 | 用途 | 关键字段 |
|---|---|---|
| `.env` | 密钥/令牌/环境变量 | `GITHUB_TOKEN`, `OPENAI_API_KEY`, `LLM_API_KEY` 等 |
| `config.yaml` | 业务配置 | `sources`, `schedule`, `storage`, `logging`, `prompt_profile`, `analysis`（含 react 配置）, `llm` |
| `config/override.example.yaml` | 覆盖配置示例 | search_keywords, source subsetting, prompt_profile override |
| `config/prompt_profiles/default.yaml` | 默认 prompt profile | 3 个任务模板映射（ReAct 的 3 个自动注入） |

### LLM 配置（config.yaml）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `llm.endpoint` | `https://api.deepseek.com` | LLM API 端点 |
| `llm.model_id` | `deepseek-v4-flash` | 模型 ID |
| `analysis.mode` | `legacy` | 分析模式（legacy/react） |
| `analysis.react.max_steps_per_group` | 5 | ReAct 每组最大步数 |
| `analysis.react.max_groups` | 10 | ReAct 最大分组数 |
| `analysis.react.enable_*` | true | 3 个 ReAct 工具开关 |

### 数据库表 (`app/storage/schema.sql`)

| 表名 | 用途 | 关键索引 |
|---|---|---|
| `run_logs` | 每批次运行元数据 | `run_date`, `status` |
| `raw_documents` | 原始抓取结果 | `url_fingerprint` (UNIQUE), `content_hash`, `run_id` |
| `news_items` | 标准化资讯 | `content_hash`, `published_at`, `run_id` |
| `entities` | 实体库 | `name`, `entity_type` |
| `news_entity_links` | 资讯-实体 M:N | `entity_id` |
| `info_chains` | 信息链 | `run_id`, `created_at` |
| `chain_evidence` | 链证据 | `chain_id`, `news_item_id` |
| `chain_scores` | 多维度评分 | `chain_id`, `run_id`, `overall DESC` |
| `prompt_profiles` | Prompt 归档 | `profile_name`, `version` (UNIQUE) |

---

## 7. 已知问题与技术债

> 详细开发规范见 `rule.md`。此处仅列出需要后续修复的代码级问题。

| # | 问题 | 严重度 | 位置 | 说明 |
|---|---|---|---|---|
| 1 | `mapping/report.py` 与 `reports/core.py` 重复 | 高 | `app/mapping/report.py`, `app/mapping/__init__.py` | 旧版缺少 risk_warnings/rationale/source_urls；`mapping/__init__.py` 仍 re-export 旧版类名 |
| 2 | 关系类型覆盖级联 | 中 | `app/chains/candidate_generation.py` | 同主题→时序→上下游逐级覆盖 `relation_to_prev`，最终只保留 `UPSTREAM_DOWNSTREAM` |
| 3 | ReAct 引擎 duck-typing | 中 | `app/analysis/react/engine.py:592-613` | `_call_llm_raw` 访问适配器私有方法，新适配器需暴露相同接口 |
| 4 | `web_access_transport.py` 无日志 | 高 | `app/collectors/web_access_transport.py` | 805 行网络 I/O 代码零日志输出 |
| 5 | 时效性评分硬编码 | 低 | `app/mapping/engine.py` | `_calculate_timeliness_score` 始终返回 80.0 |
| 6 | `use_profile` 死代码 | 低 | `app/analysis/engine.py:337-338` | `hasattr` 检查不存在的方法，永不执行 |
| 7 | ReAct 工具 2/3 为 stub | 中 | `app/analysis/react/tools.py` | `web_search` 和 `akshare_query` 返回占位数据 |
| 8 | 存储层依赖分析层 | 中 | `app/storage/database.py` | 导入 `PromptTaskType`、`PromptProfileConfig`，违反分层原则 |
| 9 | `apply_override` 不完整 | 中 | `app/config/override.py` | 解析了 `search_keywords`/`web_sources`/`prompt_overrides` 但未回写 `AppConfig` |
| 10 | `ranking/` 空模块 | 低 | `app/ranking/__init__.py` | 排序逻辑在 analysis/engine.py 内联 |
| 11 | 两个适配器响应解析重复 | 低 | `github_models.py`, `openai_compatible.py` | `_parse_response` 约 50 行逻辑重复 |
| 12 | `ChatMessage`/`PromptRenderer` 定义位置不当 | 低 | `github_models.py` | 被 `openai_compatible.py` 和 `engine.py` 依赖，应在 `contracts.py` 或独立 `types.py` |
| 13 | CDP proxy 硬编码 sleep | 低 | `web_access_transport.py:176,189` | `time.sleep(2)` / `time.sleep(3)` 等待页面加载 |
| 14 | ReAct finalize 静默吞异常 | 中 | `react/engine.py:499` | `except Exception: pass` 无日志 |

---

## 8. 按场景快速入口

### 8.1 新增采集源
1. 实现 `BaseCollector` ABC (`app/collectors/base.py`)
2. 在 `app/collectors/` 新建适配器（参考 `akshare_collector.py` 或 `web_collector.py`）
3. 在 `config.yaml` 注册来源配置
4. 写测试 `tests/test_<name>_collector.py`
5. 更新 `app/collectors/__init__.py` 导出
6. 若需要 web-access 研究采集，实现 `ResearchTransport` Protocol (`app/collectors/copilot_research_collector.py`)，参考 `web_access_transport.py`

### 8.2 调整 LLM 分析行为
1. 优先改 prompt 文件：`app/analysis/prompts/templates/*.json`
2. 或新建 `config/prompt_profiles/<profile>.yaml`
3. CLI 切换：`python -m app.main run --prompt-profile <profile>`
4. 模式切换：`python -m app.main run --analysis-mode react`（或 `config.yaml` 中 `analysis.mode`）
5. ReAct 参数 → `config.yaml` 中 `analysis.react` 节
6. ReAct 工具逻辑 → `app/analysis/react/tools.py`
7. Legacy 引擎 → `app/analysis/engine.py`
8. 适配器 → `github_models.py` 或 `openai_compatible.py`
9. 注意：`ChatMessage`/`PromptRenderer` 定义在 `github_models.py`（已知位置不当）

### 8.3 调整 A 股映射/评分权重
1. 产业链映射定义 → `app/mapping/industry_chain.py`（硬编码，修改需同步测试）
2. 映射转换逻辑 → `app/mapping/engine.py` 中 `AShareMappingEngine`
3. 5 维度评分权重 → `app/mapping/engine.py` 中 `MappingScoringEngine`（主题30% / 产业链25% / 置信度25% / 时效性10% / 覆盖度10%）
4. 日报字段输出 → `app/reports/core.py`（⚠️ 非旧版 `mapping/report.py`）

### 8.4 调整信息链构建规则
1. 同主题聚合 → `app/chains/same_topic_grouping.py`
2. 时序连接 → `app/chains/temporal_connection.py`
3. 上下游连接 → `app/chains/upstream_downstream.py`
4. 候选链流水线 → `app/chains/candidate_generation.py`
5. 注意：关系类型覆盖级联问题（见已知问题 #2）

### 8.5 调整日报格式
1. Markdown/JSON 生成器 → `app/reports/core.py`
2. 归档命名规则 → `app/reports/core.py` 中 `ReportArchiveManager`
3. ⚠️ 不要修改 `app/mapping/report.py`（旧版重复）

### 8.6 修改数据库 Schema
1. 编辑 `app/storage/schema.sql`（所有语句使用 `IF NOT EXISTS`）
2. 修改 `app/storage/database.py` 中对应 Store 类
3. 写迁移脚本（如需历史数据迁移）
4. 更新 `tests/test_storage.py`
5. 注意：无 `event_drafts` 表 — EventDraft 无持久化路径

### 8.7 排查循环导入
- 常见雷区：`app/storage/database.py` ↔ `app/analysis/`
- 已有修复案例：engine 中移除未使用的 `from app.storage import PromptProfileStore, RunLogStore`
- 策略：分析层应通过 `app/main.py` 注入 Store，避免 engine 直接 import storage

---

## 9. 版本快照

| 指标 | 数值 |
|---|---|
| Python 源文件 | ~70 个 (`app/**/*.py`) |
| 代码总行数 | ~12,000 行 |
| 测试文件 | 53 个 (`tests/test_*.py`) |
| 数据库表 | 9 张 |
| 主题标签 | 11 个 (`ThemeId`) |
| 实体类型 | 6 种 (`EntityType`) |
| 关系类型 | 4 种 (`RelationType`)，`CAUSAL` 已定义但未使用 |
| 评分维度 | 5 维 + 综合分 |
| 日报批次 | 每日 2 次 (08:30 pre-market, 14:00 midday) |
| Prompt 模板 | 6 个 (summary, chain_completion, investment_ranking, grouper, react_step, react_finalize) |
| PromptTaskType | 6 种 (SUMMARY, CHAIN_COMPLETION, INVESTMENT_RANKING, GROUPER, REACT_STEP, REACT_FINALIZE) |
| LLM 分析模式 | 双模式 (legacy 单次调用 + react 多步 ReAct) |
| ReAct 工具 | 3 个 (web_fetch 实装, web_search + akshare_query 为 stub) |
| 采集源 | 3 种 (akshare, web, copilot_research) |
| 搜索后端 | 4 级降级 (CDP Bing → HTTP Bing → Bing News → DuckDuckGo) |

---

*本索引应与代码同步维护。当新增模块、移动文件、或变更核心数据流时，请同步更新本文件。*
