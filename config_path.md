# 配置路径索引

本文档记录 mm 项目中三项关键配置的完整路径：搜索 query 词、LLM Prompt 模板、搜索与分析阶段数据源。

---

## 1. 搜索阶段 Query 词

### 1.1 默认硬编码 Query（无配置时的回退）

**文件**: `app/collectors/web_access_transport.py:60-67`

```python
_DEFAULT_AI_INVESTMENT_QUERIES = [
    "AI startup funding investment news site:techcrunch.com",
    "artificial intelligence investment VC funding site:reuters.com",
    "AI company acquisition merger site:cnbc.com",
    "AI 人工智能 投融资 新闻 site:36kr.com",
    "artificial intelligence financing round latest",
    "AI investment news today",
]
```

- **触发条件**: 当 `WebAccessTransportConfig.search_queries` 为空时，`_build_queries()` 自动使用此列表
- **使用位置**: `WebAccessTransport._build_queries()` (line 704)

### 1.2 配置覆盖 Query（通过 override YAML）

**文件**: `config/override.example.yaml:10-13`

```yaml
search_keywords:
  - "AI芯片"
  - "半导体产业政策"
  - "新能源汽车补贴"
```

- **配置加载**: `app/config/override.py` → `OverrideConfig.search_keywords`
- **Schema 定义**: `app/config/schema.py:38` → `SourcesConfig.search_keywords: list[str]`

### 1.3 Query 构建逻辑

**文件**: `app/collectors/web_access_transport.py:704-725`

```
_build_queries(request) 逻辑:
  1. 优先使用 WebAccessTransportConfig.search_queries（如有）
  2. 否则回退到 _DEFAULT_AI_INVESTMENT_QUERIES
  3. 追加 request.search_keywords，每条拼接 " AI investment news" 后缀
  4. 追加日期定向 query: "AI investment news {target_date}"
```

### 1.4 Search Keywords 传递链

```
override.yaml (search_keywords)
  → app/config/override.py (OverrideConfig.search_keywords)
    → app/main.py (_run_collection → RunContext.override)
      → app/collectors/copilot_research_collector.py (collect → ResearchRequest.search_keywords)
        → app/collectors/web_access_transport.py (_build_queries → 追加到查询列表)
```

### 1.5 WebAccessTransportConfig 自定义 Search Queries

**文件**: `app/collectors/web_access_transport.py:551`

```python
search_queries: list[str] = field(default_factory=list)
```

- 直接在构造 `WebAccessTransportConfig` 时传入自定义 query 列表
- 非空时替换 `_DEFAULT_AI_INVESTMENT_QUERIES`

### 1.6 Prompt 模板中可用的 Search Keywords

**文件**: `app/analysis/prompts/file_system_renderer.py:209`

- 搜索关键词作为上下文变量注入 LLM prompt 渲染，使 LLM 了解当前搜索范围

---

## 2. LLM Prompt 模板

### 2.1 PromptTaskType 枚举（6 种任务类型）

**文件**: `app/storage/types.py`

| 枚举值 | 用途 | 使用阶段 |
|---|---|---|
| `SUMMARY` | 摘要归纳 | Legacy 分析 |
| `CHAIN_COMPLETION` | 链路补全 | Legacy 分析 |
| `INVESTMENT_RANKING` | 投资排序 | Legacy 分析 + ReAct 跨组排序 |
| `GROUPER` | 分组策略 | ReAct Phase 1 |
| `REACT_STEP` | ReAct 单步迭代 | ReAct Phase 2 |
| `REACT_FINALIZE` | ReAct 最终输出 | ReAct Phase 3 |

### 2.2 Prompt 模板文件

**目录**: `app/analysis/prompts/templates/`

| 文件 | 对应 TaskType | 描述 |
|---|---|---|
| `summary.json` | SUMMARY | 基于证据对信息链生成简洁摘要 |
| `chain_completion.json` | CHAIN_COMPLETION | 保守推断补全缺失链路 |
| `investment_ranking.json` | INVESTMENT_RANKING | 按投资相关性对信息链排序 |
| `grouper.json` | GROUPER | 将新闻项聚类为分析分组 |
| `react_step.json` | REACT_STEP | 单步 ReAct 思考+行动+观察 |
| `react_finalize.json` | REACT_FINALIZE | 综合所有 ReAct 步骤生成最终分析 |

### 2.3 Prompt Profile 配置

**文件**: `config/prompt_profiles/default.yaml`

```yaml
profile_name: "default"
version: "1.0.0"
tasks:
  summary:
    template: "summary.json"
  chain_completion:
    template: "chain_completion.json"
  investment_ranking:
    template: "investment_ranking.json"
```

- Grouper / ReAct Step / ReAct Finalize 由 `PromptProfileConfig.from_dict()` 自动注入默认模板（grouper.json / react_step.json / react_finalize.json），无需显式配置
- **Profile 目录**: `config/prompt_profiles/`
- **模板目录**: `app/analysis/prompts/templates/`（由 `config.yaml` 的 `prompt.templates_dir` 指定）

### 2.4 模板变量/占位符

**公共变量**（所有模板共享）:

| 占位符 | 说明 |
|---|---|
| `{profile_name}` | Profile 名称 |
| `{profile_version}` | Profile 版本 |
| `{task_type}` | 当前任务类型 |
| `{analysis_payload_json}` | 信息链 + 证据 JSON |

**ReAct 专属变量**:

| 占位符 | 模板 | 说明 |
|---|---|---|
| `{react_history_json}` | react_step / react_finalize | 前序步骤历史 JSON |
| `{group_json}` | react_step | 当前分组上下文 JSON |
| `{available_tools_json}` | react_step | 可用工具 schema JSON |

### 2.5 Prompt Override（模板级定制）

**文件**: `config/override.example.yaml:35-48`

```yaml
prompt_overrides:
  system_message_suffix: "\n今日重点：AI芯片供应链动态。"  # 所有 task type 的 system 消息追加
  tasks:
    summary:
      user_message_prefix: "背景：今日发布芯片出口新规。"  # summary 任务 user 消息前缀
    investment_ranking:
      system_message: "优先评估半导体和AI产业链的投资信号。"  # 完整替换 system 消息
      user_message_suffix: "\n权重调整：AI供应链主题权重 x2。"  # user 消息后缀
```

**Override 支持 4 种修饰**:
- `system_message` — 完整替换 system 消息
- `system_message_suffix` — 追加到 system 消息末尾
- `user_message_prefix` — 前缀到 user 消息
- `user_message_suffix` — 后缀到 user 消息

### 2.6 核心加载/渲染类

| 类 | 文件 | 职责 |
|---|---|---|
| `FileSystemPromptRenderer` | `app/analysis/prompts/file_system_renderer.py` | 从磁盘加载 JSON 模板并渲染为 ChatMessage 列表 |
| `PromptProfileLoader` | `app/analysis/prompts/profile.py` | 读取并验证 YAML profile |
| `PromptProfileConfig` | `app/storage/types.py` | Profile 配置数据类，管理 task→template 映射 |
| `TaskTemplateMapping` | `app/storage/types.py` | 单个 task 的模板名 + override 配置 |

### 2.7 ReAct Prompt 上下文构建

**文件**: `app/analysis/react/prompts.py`

| 函数/类 | 对应模板 | 说明 |
|---|---|---|
| `build_grouper_prompt_context()` | grouper.json | 构建分组上下文（chains + tagged outputs） |
| `build_react_step_prompt_context()` | react_step.json | 构建单步上下文（group + history + tools） |
| `build_react_finalize_prompt_context()` | react_finalize.json | 构建汇总上下文（完整 session history） |

### 2.8 Prompt 在各分析模式中的使用路径

**Legacy 模式** (`analysis.mode: legacy`):
```
AnalysisEngine.analyse_chains()
  → adapter.analyse(AnalysisInput(prompt_profile=...))
    → FileSystemPromptRenderer.render(PromptTaskType.SUMMARY) → summary.json
    → FileSystemPromptRenderer.render(PromptTaskType.CHAIN_COMPLETION) → chain_completion.json
    → FileSystemPromptRenderer.render(PromptTaskType.INVESTMENT_RANKING) → investment_ranking.json
```

**ReAct 模式** (`analysis.mode: react`):
```
ReActAnalysisEngine.run()
  → Phase 1: _group_tagged_outputs()
    → adapter.analyse_raw(prompt_type=GROUPER) → grouper.json
  → Phase 2: _run_react_session() (per group)
    → adapter.analyse_raw(prompt_type=REACT_STEP) → react_step.json  (循环迭代)
  → Phase 3: _finalize_session()
    → adapter.analyse_raw(prompt_type=REACT_FINALIZE) → react_finalize.json
  → Phase 4: _rank_groups()
    → adapter.analyse_raw(prompt_type=INVESTMENT_RANKING) → investment_ranking.json
```

---

## 3. 搜索与分析阶段数据源

### 3.1 AkShare 数据源

#### 启用/禁用

**文件**: `config.yaml:10` → `sources.akshare: true`

#### Provider 配置

**文件**: `app/collectors/akshare_collector.py:107-110`

```python
_PROVIDERS = [
    ("cctv", "_fetch_cctv"),      # akshare.news_cctv(date)
    ("caixin", "_fetch_caixin"),  # akshare.stock_news_main_cx()
]
```

| Provider | AkShare API | 参数 | 返回字段 |
|---|---|---|---|
| cctv | `akshare.news_cctv(date)` | 日期字符串 (YYYYMMDD) | date, title, content |
| caixin | `akshare.stock_news_main_cx()` | 无 | tag, summary, url |

#### Override 筛选 Provider

**文件**: `config/override.example.yaml:18-19`

```yaml
sources:
  akshare_providers:
    - "cctv"    # 仅启用 cctv，省略则使用全部 (cctv + caixin)
```

- **Schema**: `app/config/schema.py:40` → `SourcesConfig.akshare_providers: list[str]`

### 3.2 Web/RSS 数据源

#### 启用/禁用

**文件**: `config.yaml:11` → `sources.web: true`

#### 源配置方式

WebCollector 的源列表完全通过构造函数传入，**无硬编码默认源**。

**文件**: `app/collectors/web_collector.py:377-385`

```python
def __init__(self, sources: list[dict[str, Any]] | None = None, ...):
    self._sources: list[dict[str, Any]] = sources or []
```

**源 dict 格式**:

| Key | 必填 | 说明 |
|---|---|---|
| `url` | 是 | 抓取 URL |
| `type` | 是 | `"rss"`（含 Atom）或 `"html"` |
| `provider` | 是 | 来源短标签 |
| `timeout` | 否 | 每源超时秒数（默认 15） |

#### Override 配置 Web 源

**文件**: `config/override.example.yaml:21-25`

```yaml
sources:
  web_sources:
    - url: "https://36kr.com/feed"
      type: "rss"
      provider: "36kr"
      timeout: 30
```

- **Schema**: `app/config/schema.py:42` → `SourcesConfig.override_web_sources: list[dict]`
- **运行时**: `app/main.py:86-89` — override 存在时使用 override 源，否则传入 None（空列表）

### 3.3 Copilot Research 数据源

#### 启用/禁用

**文件**: `config.yaml:13` → `sources.copilot_research: true`

#### Transport 配置

**文件**: `app/collectors/web_access_transport.py:518-555`

```python
@dataclass
class WebAccessTransportConfig:
    cdp_proxy_url: str = "http://localhost:3456"
    max_search_results: int = 10
    max_pages_to_fetch: int = 5
    fetch_timeout: int = 15
    use_cdp_for_search: bool = True
    use_cdp_for_fetch: bool = True
    search_queries: list[str] = field(default_factory=list)
    direct_sources: list[str] = field(default_factory=lambda: [
        "https://techcrunch.com/category/artificial-intelligence/",
        "https://venturebeat.com/category/ai/",
    ])
```

### 3.4 搜索引擎后端（4 级降级）

**文件**: `app/collectors/web_access_transport.py:727-783`

`WebAccessTransport._search()` 按优先级依次尝试：

| 优先级 | 后端 | URL / 端点 | 文件行号 | 说明 |
|---|---|---|---|---|
| 1 | CDP Bing | `https://www.bing.com/search?q={query}` | line 207 | 通过 CDP 浏览器代理搜索，结果最丰富 |
| 2 | HTTP Bing | `https://www.bing.com/search?q={query}&setmkt=en-US&cc=us&setlang=en` | line 298-303 | 直接 HTTP 请求 Bing，中国大陆可用 |
| 3 | Bing News | `https://www.bing.com/news/search?q={query}&setmkt=en-US&cc=us&qft=interval%3d%227%22&format=rs&count={n}` | line 360-367 | Bing 新闻垂直搜索，7 天内新闻 |
| 4 | DuckDuckGo | `https://html.duckduckgo.com/html/` (POST, `q={query}&kl=us-en`) | line 418-421 | 最后回退，中国大陆可能不可达 |

### 3.5 直接抓取源（Direct Sources）

**文件**: `app/collectors/web_access_transport.py:552-555`

```python
direct_sources: list[str] = field(default_factory=lambda: [
    "https://techcrunch.com/category/artificial-intelligence/",
    "https://venturebeat.com/category/ai/",
])
```

- Transport 在搜索之外额外直接抓取这些页面，提取文章链接
- 可通过 `WebAccessTransportConfig.direct_sources` 自定义

### 3.6 ReAct 工具数据源

**文件**: `app/analysis/react/tools.py`

| 工具名 | 数据源 | 启用配置 | 说明 |
|---|---|---|---|
| `web_search` | 复用 WebAccessTransport 4 级搜索后端 | `analysis.react_enable_web_search` | 搜索 query 由 LLM 动态生成 |
| `web_fetch` | HTTP GET 任意 URL | `analysis.react_enable_web_fetch` | 抓取 URL 内容，截取前 2000 字符 |
| `akshare_query` | `akshare.stock_zh_a_hist(symbol, period="daily", adjust="qfq")` | `analysis.react_enable_akshare_query` | 查询 A 股历史行情数据 |

**工具启用开关** (`config.yaml:88-90`):

```yaml
analysis:
  react:
    enable_web_search: true
    enable_web_fetch: true
    enable_akshare_query: true
```

### 3.7 LLM API 端点

**文件**: `config.yaml:44-51`

```yaml
llm:
  endpoint: https://api.deepseek.com
  model_id: deepseek-v4-flash
  # api_key_env_var: LLM_API_KEY  (从 .env 读取)
  response_format: null
```

- **Adapter**: `app/analysis/adapters/openai_compatible.py`（endpoint 非空时使用）
- **Legacy fallback**: `app/analysis/adapters/github_models.py`（endpoint 为空时使用 GitHub Models）

---

## 4. 配置入口速查表

| 配置项 | 主配置文件 | Override 文件 | Schema 定义 | 运行时入口 |
|---|---|---|---|---|
| 搜索关键词 | — | `override.yaml: search_keywords` | `SourcesConfig.search_keywords` | `CopilotResearchCollector` → `ResearchRequest.search_keywords` |
| Transport 自定义 query | — | — | `WebAccessTransportConfig.search_queries` | `WebAccessTransport._build_queries()` |
| AkShare 启用 | `config.yaml: sources.akshare` | — | `SourcesConfig.akshare` | `main.py: _create_collectors()` |
| AkShare Provider 筛选 | — | `override.yaml: sources.akshare_providers` | `SourcesConfig.akshare_providers` | `AkShareCollector.collect()` |
| Web 源列表 | — | `override.yaml: sources.web_sources` | `SourcesConfig.override_web_sources` | `main.py: _create_collectors()` |
| Copilot Research 启用 | `config.yaml: sources.copilot_research` | — | `SourcesConfig.copilot_research` | `main.py: _create_collectors()` |
| Prompt Profile | `config.yaml: prompt.default_profile` | `override.yaml: prompt_profile` | `PromptConfig.default_profile` | `PromptProfileLoader` |
| Prompt 模板目录 | `config.yaml: prompt.templates_dir` | — | `PromptConfig.templates_dir` | `FileSystemPromptRenderer` |
| Prompt Override | — | `override.yaml: prompt_overrides` | `PromptConfig.prompt_override` | `FileSystemPromptRenderer` |
| ReAct 工具开关 | `config.yaml: analysis.react.enable_*` | — | `AnalysisConfig.react_enable_*` | `ReActAnalysisEngine` |
| LLM 端点 | `config.yaml: llm.endpoint` | — | `LLMConfig.endpoint` | `OpenAICompatibleAdapter` |
| LLM 模型 | `config.yaml: llm.model_id` | — | `LLMConfig.model_id` | Adapter 构造 |
