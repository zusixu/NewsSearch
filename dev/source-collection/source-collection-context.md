# source-collection

## 关键文件

- `app/collectors/raw_document.py` — `RawDocument` 统一原始文档结构（已完成）
- `app/collectors/base.py` — 统一采集器接口（已完成）
- `app/collectors/__init__.py` — 导出接口符号（已完成；新增 `RawDocument` / ResearchRequest / ResearchResponse / ResearchTransport / NullTransport / `CollectionCache`）
- `app/collectors/akshare_collector.py` — AkShare 采集器（已完成，含 CCTV + Caixin 两路 provider；新增 `cache` 构造参数）
- `app/collectors/web_collector.py` — 公开网页采集器（已完成，支持 RSS/Atom 与静态 HTML 两种采集模式，来源可配置；新增 `cache` 构造参数）
- `app/collectors/copilot_research_collector.py` — 研究型采集器接口层（已完成；传输层协议已定义；新增 `cache` 构造参数）
- `app/collectors/collection_cache.py` — 采集缓存（新建）
- `tests/test_collector_interface.py` — 接口层测试（40 个用例全部通过）
- `tests/test_akshare_collector.py` — AkShare 采集器专项测试（45 个用例全部通过，全部 mock，无网络调用）
- `tests/test_web_collector.py` — WebCollector 专项测试（83 个用例全部通过，全部本地 fixture / mock，无网络调用）
- `tests/test_copilot_research_collector.py` — Research collector 接口层专项测试（63 个用例全部通过，全部 fake/mock，无网络调用）
- `tests/test_collection_cache.py` — 采集缓存专项测试（新建；129 个用例全部通过）
- `data/raw/`（已创建，原始文档落盘目录；亦是缓存根目录）

## 决策记录

- AkShare 作为主采集源之一。
- web-access 是每日自动任务的固定研究来源，必须接入主流程。
- 自动化每日任务中，`web-access` 每次都要调用。
- AkShare 实现前已查阅官方文档与本地环境（akshare 1.18.57）：
  - `news_cctv(date: str)` → DataFrame（date, title, content）
  - `stock_news_main_cx()` → DataFrame（tag, summary, url）
  - 两者参数最少、覆盖面广，选作首批 provider。
- WebCollector 设计为来源可配置（`sources` 构造参数），不硬编码任何 URL；
  首批来源名单是独立的后续决策，已在「待补充」中记录。
- CopilotResearchCollector 采用依赖注入（`ResearchTransport` 协议）隔离传输层，
  真实的 web-access 执行可在不修改采集器逻辑的情况下通过注入不同的 transport 实现；
  当前默认 transport 为 `NullTransport`，调用时抛出 `CollectorUnavailableError`。

## web-access 强制调度说明

**`web-access` 是每日管道的强制调度组件，不是可选增强。**
`CopilotResearchCollector.is_enabled()` 永远返回 `True`，无论 `sources_config` 如何设置均不可禁用。

本节点（「定义 research collector 接口」）**仅定义集成契约**，不实现真实的 web-access 网络调用。
真实传输层的对接是后续独立任务，在 transport 层就绪后注入 `CopilotResearchCollector` 即可生效。

## 外部参考

- AkShare 文档：`https://akshare.akfamily.xyz/`
- AkShare GitHub：`https://github.com/akfamily/akshare`

## 查阅要求

- 开发 AkShare 相关接口前，优先查阅官方文档与仓库说明；
- 重点确认函数名、参数、频率限制、返回字段和示例；
- 不确定时应以官方文档为准。

## 待补充

- **首批 WebCollector 来源名单**（URL、类型、provider 标签）——当前 WebCollector
  已可接受任意来源列表，名单本身是独立的后续决策，需在完成 research collector 接口后统一规划。
- 采集频率和限流策略。

## 当前进度

- **已完成**：`定义统一采集器接口`
  - `app/collectors/base.py`：定义了 `RunContext`、`CollectResult`、`CollectorError` 及四个子类、`BaseCollector` ABC。
  - 三个存根文件已接入接口，`CopilotResearchCollector.is_enabled()` 强制返回 `True`（mandatory 组件）。

- **已完成**：`接入 AkShare 采集器`
  - 实现前已查阅 AkShare 官方文档并确认本地环境（akshare 1.18.57）中 `news_cctv` 和 `stock_news_main_cx` 两个函数的签名、参数与返回字段。
  - `app/collectors/akshare_collector.py`：
    - `_import_akshare()` 懒加载函数，import 失败时抛出 `CollectorUnavailableError`。
    - `_safe_str()` 辅助函数，处理 pandas NaN/NA 值。
    - `AkShareCollector.collect()`：顺序调用两路 provider，单路失败记入 `CollectResult.errors`，不中断其他 provider；全路失败时 `result.failed == True`；metadata 含 `date_str` 和 `provider_counts`。
    - `_fetch_cctv()`：调用 `news_cctv(date=date_str)`，归一化为 `{source, provider, title, content, url=None, date}` 字典。
    - `_fetch_caixin()`：调用 `stock_news_main_cx()`，归一化时以 `tag` 为 title，`summary` 为 content，日期取 `target_date.isoformat()`。
  - `tests/test_akshare_collector.py`：45 个专项测试（全 mock，无网络），覆盖正常路径、单路/双路失败、import 失败、空 DataFrame、字段归一化、is_enabled 合约。
  - `tests/test_collector_interface.py`：移除了 `test_akshare_collect_raises_not_implemented`（存根已实现）；其余接口测试全部通过。

- **已完成**：`接入公开网页采集器`
  - `app/collectors/web_collector.py`（全量重写，替换存根）：
    - `parse_feed()`：解析 RSS 2.0 和 Atom feed，支持 `content:encoded`、pubDate（RFC-2822）、Atom `published`/`updated`（ISO-8601）、无命名空间 Atom；缺失日期回退至 `fallback_date`。
    - `parse_html()`：使用 `_HeadingExtractor`（stdlib `html.parser` 子类）按 h1/h2/h3 分段提取标题与正文；跳过 script/style/nav/footer/head；`convert_charrefs=True` 自动解码 HTML 实体。
    - `fetch_url()`：stdlib `urllib.request` 封装，将 HTTPError / URLError / OSError 统一转换为 `CollectorUnavailableError`。
    - `WebCollector`：构造函数接收 `sources: list[dict]`（可配置，不硬编码来源）；逐源独立采集，单源失败记入 `CollectResult.errors` 不中断其他源；metadata 含 `source_counts`；`is_enabled()` 尊重 `sources_config.web`。
    - **首批来源名单为后续独立决策**，当前实现不含任何硬编码 URL，已在「待补充」中记录。
  - `tests/test_web_collector.py`：83 个专项测试（本地 fixture + mock，无网络），覆盖 RSS/Atom/HTML 解析、日期解析辅助函数、fetch_url 错误路径、collect() 全通/单源失败/全失败/边界情况、is_enabled 合约、metadata 校验。
  - `tests/test_collector_interface.py`：移除了已过时的 `test_web_collect_raises_not_implemented`。
  - 全部 168 个测试通过。

- **已完成**：`定义 research collector 接口`
  - `app/collectors/copilot_research_collector.py`（全量重写，替换存根）：
    - `ResearchRequest`（frozen dataclass）：`prompt_profile`、`target_date`、`run_id`、`dry_run`；封装传给 transport 的不可变请求束。
    - `ResearchResponse`（dataclass）：`items`、`provider`、`error`；transport 返回的响应结构，`error` 为非 None 时代表非致命错误。
    - `ResearchTransport`（ABC）：定义 `execute(request) -> ResearchResponse` 抽象方法；传输层与采集器完全解耦。
    - `NullTransport`：默认占位 transport，调用 `execute()` 时抛出 `CollectorUnavailableError`（可重试），不抛 `NotImplementedError`。
    - `CopilotResearchCollector`：构造函数接收 `transport` 参数（默认 `NullTransport`）；`collect()` 将 `ctx.prompt_profile`、`ctx.target_date`、`ctx.run_id`、`ctx.dry_run` 全部转发给 transport；结果归一化后填入 `CollectResult`，metadata 含 `provider`、`prompt_profile`、`item_count`；`is_enabled()` 永远返回 `True`。
    - `_normalise_item()`：将 transport 返回的 raw dict 归一化为临时 dict schema（source/provider/title/content/url/date/query），无 title 且无 content 的条目丢弃。
  - `app/collectors/__init__.py`：新增导出 `ResearchRequest`、`ResearchResponse`、`ResearchTransport`、`NullTransport`。
  - `tests/test_copilot_research_collector.py`（新建）：63 个专项测试，全部 fake/mock，无网络调用；覆盖 ResearchRequest 冻结性/字段、ResearchResponse 默认值/实例隔离、ResearchTransport ABC 执行、NullTransport 错误合约、collect() 正常路径/prompt-profile 转发/dry_run 转发/metadata 校验/部分失败/transport 异常传播、_normalise_item 全路径。
  - `tests/test_collector_interface.py`：将 `test_copilot_research_collect_raises_not_implemented` 更新为 `test_copilot_research_collect_raises_unavailable_without_transport`（`CollectorUnavailableError`）。
  - source-collection 相关测试共 231 个全部通过；当前仓库总计 302 个测试全部通过。
  - **注意**：`web-access` 仍是每日强制调度组件；本节点仅定义集成契约，真实 web-access 执行待后续 transport 实现后注入。

- **已完成**：`统一原始文档结构`
  - `app/collectors/raw_document.py`（新建）：
    - `RawDocument` dataclass（可变，非 frozen）：`source`、`provider`、`title`、`content: str | None`、`url: str | None`、`date`（ISO-8601 字符串）、`metadata: dict[str, Any]`（默认空 dict，存放来源特定字段）。
    - `query` 字段（research collector 独有）存入 `metadata={"query": ...}`，保持核心 schema 对所有 collector 一致。
  - `app/collectors/base.py`：`CollectResult.items` 类型从 `list[dict[str, Any]]` 改为 `list[RawDocument]`，移除「TEMPORARY CONTRACT」注释。
  - `app/collectors/__init__.py`：新增 `RawDocument` 导出。
  - 三个 collector 全部更新：`akshare_collector.py`、`web_collector.py`、`copilot_research_collector.py` 内部均改为返回 `RawDocument` 实例；transport 层输入（`ResearchResponse.items`）仍保持 `list[dict]`，dict → `RawDocument` 转换在 `_normalise_item()` 中完成。
  - 三个测试文件全部更新：`test_akshare_collector.py`、`test_web_collector.py`、`test_copilot_research_collector.py` 中所有 `item["field"]` dict 访问改为 `item.field` 属性访问；`query` 字段改为 `item.metadata["query"]`；`test_item_schema_keys` 改用 `hasattr` 检查。
  - 全部 231 个采集器相关测试通过，仓库总计 231 个测试全部通过（0 失败）。

- **已完成**：`增加采集缓存`
  - `app/collectors/collection_cache.py`（新建）：
    - `CollectionCache` 类：可注入的文件系统缓存，根目录默认为 `data/raw/`，路径结构为 `{root}/{source}/{date_str}/{cache_key}.json`。
    - `get(source, date, cache_key) -> list[RawDocument] | None`：缓存读取，miss 或任何读取错误均返回 `None`，不抛异常。
    - `put(source, date, cache_key, items)`：缓存写入，自动创建父目录；空列表亦为有效缓存条目。
    - `exists(source, date, cache_key) -> bool`：检查缓存文件是否存在。
    - `cache_path(source, date, cache_key) -> Path`：返回缓存文件路径（可能不存在）。
    - `_sanitize_key()`：将缓存 key 中不安全字符替换为下划线。
    - `_doc_to_dict()` / `_dict_to_doc()`：`RawDocument` ↔ plain dict 序列化，支持全字段含 `metadata` 嵌套 dict。
  - 缓存文件落盘位置：
    - AkShareCollector：`data/raw/akshare/{date}/full_run.json`（每日整体缓存）
    - WebCollector：`data/raw/web/{date}/{provider}.json`（每个 provider 独立缓存）
    - CopilotResearchCollector：`data/raw/copilot_research/{date}/{prompt_profile}.json`（每个 prompt profile 独立缓存）
  - 三个 collector 均新增 `cache: CollectionCache | None = None` 构造参数（可选注入）：
    - 缓存命中时直接返回，不调用外部 API / 网络；`metadata["from_cache"] = True` 标记（AkShare / Research）。
    - 缓存未命中时正常采集，采集到 items 后写入缓存（无 items 时不写入）。
    - 未注入 cache 时行为与原来完全一致（向后兼容）。
  - `app/collectors/__init__.py`：新增 `CollectionCache` 导出。
  - `tests/test_collection_cache.py`（新建）：58 个专项测试，全部 offline；覆盖：
    - `_sanitize_key`、`_doc_to_dict`、`_dict_to_doc` 辅助函数全路径；
    - `CollectionCache` 路径结构、exists、put（目录创建/覆盖/空列表/metadata 序列化）、get（miss/hit/corrupt JSON/non-list root/缺字段/多条目/Unicode）；
    - AkShareCollector：miss → 写缓存、hit → 跳过 AkShare 调用、from_cache 标记、无 items 不写缓存；
    - WebCollector：miss → 写缓存、hit → 跳过 fetch、混合命中、fetch error 不写缓存；
    - CopilotResearchCollector：miss → 写缓存、hit → 跳过 transport、from_cache 标记、prompt_profile 为 cache key、不同 profile 独立缓存、无 items 不写缓存、metadata.query 保留。
  - 仓库全部 360 个测试通过（0 失败）。

- **已完成**：`增加失败重试`
  - `app/collectors/retry.py`（新建）：
    - `with_retry(fn, *, max_attempts=3, backoff_base=1.0, sleeper=time.sleep) -> T`：通用重试工具函数。
    - 仅重试 `CollectorError` 且 `retryable=True` 的错误；非 retryable 错误和非 `CollectorError` 异常立即传播。
    - 指数退避：`backoff_base * 2 ** attempt` 秒（最后一次尝试后不 sleep）；`sleeper` 参数可注入用于确定性测试。
  - `app/collectors/base.py`：所有四个 `CollectorError` 子类均新增 `*, retryable: bool = <default>` 关键字参数，允许覆盖默认 retryable 标志；向后兼容（现有调用者不需传入）。
  - `app/collectors/copilot_research_collector.py`：
    - `NullTransport.execute()` 改为抛出 `CollectorUnavailableError(retryable=False)`（配置失败非瞬态，不应重试）。
    - `CopilotResearchCollector.__init__` 新增 `max_attempts=3, sleeper=None` 参数；`collect()` 中 `transport.execute()` 调用包裹在 `with_retry` 中。
  - `app/collectors/akshare_collector.py`：`__init__` 新增 `max_attempts=3, sleeper=None` 参数；每路 provider 调用（`_fetch_cctv`/`_fetch_caixin`）均包裹在 `with_retry` 中；lambda 使用默认参数捕获以避免闭包-in-loop bug。
  - `app/collectors/web_collector.py`：`__init__` 新增 `max_attempts=3, sleeper=None` 参数；每个 source 的 `_collect_one()` 调用包裹在 `with_retry` 中。
  - `app/collectors/__init__.py`：新增 `with_retry` 导出。
  - `tests/test_retry.py`（新建）：覆盖 `with_retry` 单元测试（立即成功、一次重试后成功、全部失败、不重试非 retryable 错误、不重试非 CollectorError 异常、退避时序、sleeper 注入、max_attempts=1）；以及三个 collector 的重试集成测试（可注入 `sleeper=lambda _: None` 消除延迟）。
  - `tests/test_copilot_research_collector.py`：将 `test_error_is_retryable` 改为断言 `retryable is False`（NullTransport 变更）。
  - `tests/test_web_collector.py`：`TestWebCollectorPartialFailure` 中各测试的 `side_effect` 列表更新为提供足够的 `err` 条目（每个失败 source 的每次重试均需一条）。
  - `tests/test_retry.py`：33 个专项测试通过；当前仓库总计 360 个测试通过（0 失败）。
  - **注意**：`_fetch_cctv` / `_fetch_caixin` 内部将所有 AkShare 异常包裹为 `CollectorUnavailableError(retryable=True)`，因此所有 provider 异常均会被重试（符合预期）。

## 下一步

- **source-collection 模块全部 7 个 checklist 节点已完成。**
- 推荐直接切换到下一个子任务：`normalization-pipeline`
  - 优先把 `RawDocument` 接到 `NewsItem` / `EventDraft`；
  - 然后补 URL 去重、文本哈希去重、时间标准化、来源可信度分级；
  - 当前 source-collection 的 collector 输出、缓存、重试基础已经齐备，可直接作为归一化输入层。
- 若后续 AI 希望先补齐采集侧运营化细节，再进入归一化，则优先补充：
  - WebCollector 首批来源名单（URL、type、provider 标签）；
  - 采集频率与限流策略。

## 暂停前总结

- `project-bootstrap` 已全部完成；
- `source-collection` 已全部完成；
- 当前已具备：
  - 统一 collector 接口；
  - AkShare / 公共网页 / Copilot research 三类采集器能力；
  - `RawDocument` 统一原始文档结构；
  - 文件系统原始缓存（`data/raw/`）；
  - 仅针对瞬时错误的通用重试；
  - 共 360 个测试全部通过。

## 交接要求

- 上下文快用完时，先回写当前进度、修改文件、阻塞项和下一步，再切换新的子智能体。
