# normalization-pipeline

## 关键文件

- `app/models/raw_document.py` — `RawDocument` 的规范定义（已创建）
- `app/models/news_item.py` — `NewsItem` 的规范定义（已创建）
- `app/models/event_draft.py` — `EventDraft` 的规范定义（已创建）
- `app/models/__init__.py` — 模型包入口，导出 `RawDocument`、`NewsItem` 和 `EventDraft`（已更新）
- `app/collectors/raw_document.py` — 向后兼容再导出 shim（已改写，不再含定义）
- `app/normalize/url_dedup.py` — `canonicalize_url` 和 `deduplicate_by_url` 的实现（已创建）
- `app/normalize/__init__.py` — 归一化流水线包，声明 `RawDocument` 为输入契约、`NewsItem` 和 `EventDraft` 为输出契约（已更新）
- `tests/test_raw_document.py` — 针对 `RawDocument` 的专项测试（已创建，11 个用例全部通过）
- `tests/test_news_item.py` — 针对 `NewsItem` 的专项测试（已创建，29 个用例全部通过）
- `tests/test_event_draft.py` — 针对 `EventDraft` 的专项测试（已创建，37 个用例全部通过）
- `tests/test_url_dedup.py` — 针对 URL 去重的专项测试（已创建，48 个用例全部通过）
- `app/normalize/_item_merge.py` — shared `merge_news_items` helper used by both URL and text dedup (已创建)
- `app/normalize/text_dedup.py` — `text_fingerprint`、`deduplicate_by_text` 的实现（已创建）
- `tests/test_text_dedup.py` — 针对文本哈希去重的专项测试（已创建，51 个用例全部通过）
- `app/normalize/time_norm.py` — `parse_date_string`、`normalize_item_time`、`normalize_time` 的实现（已创建）
- `tests/test_time_norm.py` — 针对时间标准化的专项测试（已创建，87 个用例全部通过）
- `app/normalize/source_credibility.py` — `grade_item_credibility` 和 `grade_credibility` 的实现（已创建）
- `tests/test_source_credibility.py` — 针对来源可信度分级的专项测试（已创建，80 个用例全部通过）

- **自主决策记录（来源可信度分级）**：用户不在场，评分规则集保守制定，8 条规则按顺序匹配（首中即止）：Rule 1 = URL 域名含官方模式 → 5；Rule 2 = provider 含官方 token → 5；Rule 3 = provider 含知名媒体 token → 4；Rule 4 = URL 域名含知名媒体模式 → 4；Rule 5 = source 为 copilot_research 或 provider 含 web-access → 1（先于 Rule 6–7 检查，避免被提升）；Rule 6 = source 为 akshare → 3；Rule 7 = source 为 web → 2；Rule 8 = 兜底 → 0。结果存入 `metadata["source_credibility"]`，含 `score`、`label`、`matched_rule`、`reason` 四个字段。原始 `NewsItem` 永不修改，始终返回新实例。
- **自主决策记录（时间标准化）**：用户不在场，回退顺序自主选定为：先试 `item.published_at`，再按索引顺序逐个试 `item.raw_refs[i].date`，全部失败则以空字符串 `""` 为哨兵值，并在 `metadata["time_normalization"]` 中记录完整的尝试日志（含每个来源的原始值和解析结果）。格式支持范围保守选定为：ISO 日期/ISO 日期时间前缀、YYYY/MM/DD（允许不补零）、YYYYMMDD（严格 8 位）、RFC-2822（委托 `email.utils.parsedate`）、中文 YYYY年M月D日（允许不补零）。
- 去重应同时考虑 URL 和文本内容。
- 标准化结果应保留原始来源引用，便于回溯。
- `RawDocument` 的规范位置定为 `app/models/`，而非 `app/collectors/`，理由：
  - 它是跨层契约（采集层产生、归一化层消费），不应归属于任一具体层；
  - `app/collectors/raw_document.py` 保留为 shim，确保现有采集器代码零改动；
  - `app/normalize` 通过 `from app.models import RawDocument` 建立流水线输入契约。
- 所有三条导入路径（`app.models`、`app.collectors.raw_document`、`app.normalize`）指向同一个 class 对象，由测试 `TestImportIdentity` 强制验证。
- `NewsItem` 是归一化阶段的输出结构，位于 `app/models/news_item.py`：
  - 通过 `raw_refs: list[RawDocument]` 保留所有原始文档引用（支持单源和多源合并）；
  - 提供 `from_raw(raw)` 工厂方法，实现零转换地从单个 `RawDocument` 构建 `NewsItem`；
  - `from_raw` 对 metadata 做浅拷贝，确保 `NewsItem` 和 `RawDocument` 的 metadata 相互独立；
  - 实际字段清洗（文本归一化、日期解析、可信度评分等）由后续 pipeline 节点负责，`NewsItem` 本身不做任何转换；
  - `app.models`、`app.normalize` 的导入路径均指向同一 class 对象，由 `test_news_item.py` 的 `TestImportIdentity` 强制验证。

## RawDocument → NewsItem → EventDraft 三段式进展

```
RawDocument  →  NewsItem  →  EventDraft  →  …
（采集层产出）   （归一化层产出）  （事件抽取层产出）
```

### RawDocument（第一阶段，已完成）
- 每个采集器（AkShare、Web、CopilotResearch）的统一输出类型
- 字段：`source`、`provider`、`title`、`content`、`url`、`date`、`metadata`
- 规范位置：`app/models/raw_document.py`；采集层通过 shim 保持向后兼容

### NewsItem（第二阶段，已完成）
- 归一化流水线的输出类型，由一个或多个 `RawDocument` 派生
- 字段：`title`、`content`、`url`、`published_at`、`source`、`provider`、`raw_refs`、`metadata`
- `raw_refs: list[RawDocument]` 始终非空，保存所有贡献该条新闻的 `RawDocument` 实例
- `from_raw(raw)` 工厂方法以零转换方式从单个 `RawDocument` 构建 `NewsItem`
- 规范位置：`app/models/news_item.py`

### EventDraft（第三阶段，已完成）
- 事件抽取阶段的输出类型，由一个或多个 `NewsItem` 派生
- 字段：`title`、`summary`、`occurred_at`、`source_items`、`entities`、`themes`、`metadata`
- `source_items: list[NewsItem]` 始终非空，保存所有贡献该事件的 `NewsItem` 实例
- `from_news_item(item)` 工厂方法以零转换方式从单个 `NewsItem` 构建 `EventDraft`
- `entities` 和 `themes` 默认为空列表，由后续实体标注/主题标注阶段填充
- 全链路回溯：`EventDraft.source_items[n].raw_refs[m]` 可追溯到原始 `RawDocument`
- 规范位置：`app/models/event_draft.py`

## 待补充

- 标题与正文清洗策略。

## 当前进度

- [x] **定义原始文档结构**（已完成）
  - `RawDocument` 已从 `app/collectors/raw_document.py` 提升为 `app/models/raw_document.py` 中的共享模型
  - 采集层 shim 保持向后兼容，现有所有采集器代码无需修改
  - `app/normalize/__init__.py` 已声明 `RawDocument` 为归一化流水线输入契约
  - 新增专项测试 `tests/test_raw_document.py`（11 个用例全部通过）

- [x] **定义标准资讯结构**（已完成）
  - `NewsItem` 定义于 `app/models/news_item.py`
  - 字段：`title`、`content`、`url`、`published_at`、`source`、`provider`、`raw_refs`、`metadata`
  - `raw_refs: list[RawDocument]` 保存所有原始文档引用，支持单源和多源合并场景
  - `from_raw(raw)` 工厂方法以零转换方式从单个 `RawDocument` 构建 `NewsItem`
  - `app.models` 和 `app.normalize` 均导出 `NewsItem`
  - 新增专项测试 `tests/test_news_item.py`（29 个用例全部通过）
  - 独立验证子智能体已完成导出一致性验证：`app.models.NewsItem is app.normalize.NewsItem`

- [x] **定义事件草稿结构**（已完成）
  - `EventDraft` 定义于 `app/models/event_draft.py`
  - 字段：`title`、`summary`、`occurred_at`、`source_items`、`entities`、`themes`、`metadata`
  - `source_items: list[NewsItem]` 保存所有贡献事件的 `NewsItem` 引用，支持单源和多源合并场景
  - `from_news_item(item)` 工厂方法以零转换方式从单个 `NewsItem` 构建 `EventDraft`
  - `entities` 和 `themes` 默认为空列表，由后续阶段（实体标注、主题标注）填充
  - `app.models` 和 `app.normalize` 均导出 `EventDraft`
  - 全链路回溯路径：`EventDraft.source_items[n].raw_refs[m]` → `RawDocument`，经测试强制验证
  - 新增专项测试 `tests/test_event_draft.py`（37 个用例全部通过）
  - 独立验证子智能体已完成 `EventDraft` 导出与兼容性验证：`tests/test_event_draft.py` 37/37 通过，`tests/test_news_item.py` + `tests/test_raw_document.py` 40/40 通过

- [x] **实现 URL 去重**（已完成）
  - `app/normalize/url_dedup.py` 实现 `canonicalize_url` 和 `deduplicate_by_url`
  - 保守 URL 规范化：scheme/host 小写化、移除 fragment、移除默认端口、空路径归一为 "/"、安全剥离尾部斜杠、query 参数排序；不丢弃任意 query 参数
  - 输入 `list[NewsItem]`，输出去重后的 `list[NewsItem]`；`url=None` 的条目直接透传，不参与去重
  - 保留可追溯性：合并后的 `NewsItem.raw_refs` 包含所有贡献来源（代表项的 raw_refs 在前）
  - 稳定排序：首次出现的代表项保持在输出序中的位置，后续重复项不影响位置
  - 字段填充：仅在代表项字段为 None / 空字符串时，从第一个有值的重复项填充（保守合并）
  - metadata 浅合并：代表项已有 key 不被覆盖，仅从重复项补充缺失 key
  - 原始 `NewsItem` 实例不被修改；合并后产生新对象
  - `canonicalize_url` 和 `deduplicate_by_url` 均从 `app.normalize` 导出
  - 新增专项测试 `tests/test_url_dedup.py`（48 个用例全部通过）
  - 独立验证子智能体已完成 URL 去重节点验收：`tests/test_url_dedup.py` 48/48 通过，`tests/test_raw_document.py` + `tests/test_news_item.py` + `tests/test_event_draft.py` 77/77 通过

- [x] **实现文本哈希去重**（已完成）
  - **自主决策记录**：用户不在场，哈希作用域自主选定为 **title + body**
  - 新增内部共享模块 `app/normalize/_item_merge.py`，提取 `merge_news_items` 函数，统一 URL 去重与文本去重的合并语义
  - `app/normalize/text_dedup.py` 实现：
    - `_normalize_text(text)` — Unicode NFC 规范化 → `casefold` → 空白字符折叠（包含零宽字符）
    - `_is_blank(title, content)` — 判断 title+content 规范化后是否为空；空白条目直接透传
    - `text_fingerprint(title, content)` — 基于 `title + "\\n" + content` 的 SHA-256 指纹
    - `deduplicate_by_text(items)` — 按文本指纹去重，合并 `raw_refs`，保持首现顺序稳定
  - `url_dedup.py` 已改为复用共享 merge helper，URL 去重行为保持不变
  - `text_fingerprint` 和 `deduplicate_by_text` 均已从 `app.normalize` 导出
  - 新增专项测试 `tests/test_text_dedup.py`（51 个用例全部通过）
  - 独立验证子智能体已完成文本哈希去重节点验收；随后本地复核命令：
    - `conda run -n quant pytest tests/test_raw_document.py tests/test_news_item.py tests/test_event_draft.py tests/test_url_dedup.py tests/test_text_dedup.py -q`
    - 实际结果：**176/176 通过**

- [x] **实现时间标准化**（已完成）
  - **自主决策**：回退顺序选定为先试 `item.published_at`，再按索引顺序逐个试 `item.raw_refs[i].date`，全部失败则以空字符串 `""` 为哨兵值，并在 `metadata["time_normalization"]` 记录完整尝试日志。
  - `app/normalize/time_norm.py` 实现：
    - `parse_date_string(s)` — 将原始日期字符串解析为 `"YYYY-MM-DD"`，支持五种格式，按顺序尝试（详见模块文档）；通过 `datetime()` 构造函数验证日历合法性
    - `normalize_item_time(item)` — 对单个 `NewsItem` 执行时间标准化，返回新实例；永不修改输入
    - `normalize_time(items)` — 批量形式，保持顺序和数量
  - 支持格式（保守范围）：ISO 日期/日期时间前缀、`YYYY/MM/DD`（允许不补零）、`YYYYMMDD`（严格 8 位）、RFC-2822（委托 `email.utils.parsedate`）、中文 `YYYY年M月D日`（允许不补零）
  - 所有输出项的 `metadata["time_normalization"]` 包含：`status`、`original`、`normalized`、`fallback_source`、`attempts`
  - `parse_date_string`、`normalize_item_time`、`normalize_time` 均已从 `app.normalize` 导出
  - 新增专项测试 `tests/test_time_norm.py`（87 个用例全部通过）
  - 独立验证子智能体已完成时间标准化节点验收：`tests/test_time_norm.py` 87/87 通过，既有归一化专项测试 176/176 通过
  - 本地复核命令：
    - `conda run -n quant pytest tests/test_raw_document.py tests/test_news_item.py tests/test_event_draft.py tests/test_url_dedup.py tests/test_text_dedup.py tests/test_time_norm.py -q`
    - 实际结果：**263/263 通过**

- [x] **实现来源可信度分级**（已完成）
  - `app/normalize/source_credibility.py` 实现：
    - `grade_item_credibility(item)` — 对单个 `NewsItem` 评级，返回新实例；永不修改输入
    - `grade_credibility(items)` — 批量形式，保持顺序和数量
  - 评分方案（0–5，保守确定性规则，8 条有序规则，首中即止）：
    - Rule 1: URL 域名含官方模式（gov.cn、xinhuanet.com、people.com.cn、各交易所等）→ 5
    - Rule 2: provider 含官方 token（xinhua、gov、csrc、sse 等）→ 5
    - Rule 3: provider 含知名媒体 token（cctv、caixin、bloomberg、reuters、21jingji、yicai 等）→ 4
    - Rule 4: URL 域名含知名媒体模式（cctv.com、caixin.com、bloomberg.com 等）→ 4
    - Rule 5: source == "copilot_research" 或 provider 含 "web-access" → 1（先于 Rule 6–7，防止误升）
    - Rule 6: source == "akshare" → 3
    - Rule 7: source == "web" → 2
    - Rule 8: 兜底 → 0
  - 输出 `metadata["source_credibility"]` 含：`score`（int）、`label`（str）、`matched_rule`（str）、`reason`（str）
  - `grade_item_credibility` 和 `grade_credibility` 均已从 `app.normalize` 导出
  - 新增专项测试 `tests/test_source_credibility.py`（80 个用例全部通过）
  - 本地复核命令：
    - `conda run -n quant pytest tests/test_raw_document.py tests/test_news_item.py tests/test_event_draft.py tests/test_url_dedup.py tests/test_text_dedup.py tests/test_time_norm.py tests/test_source_credibility.py -q`
    - 实际结果：**343/343 通过**

- [x] **当前专项测试汇总**（normalization-pipeline 全部完成）
  - `tests/test_raw_document.py`：11 个用例
  - `tests/test_news_item.py`：29 个用例
  - `tests/test_event_draft.py`：37 个用例
  - `tests/test_url_dedup.py`：48 个用例
  - `tests/test_text_dedup.py`：51 个用例
  - `tests/test_time_norm.py`：87 个用例
  - `tests/test_source_credibility.py`：80 个用例
  - 上述七个专项测试文件共 **343 个用例，全部通过**（已实际运行验证）

## 下一步

- **normalization-pipeline 全部七个 checklist 节点均已完成。**
- 推荐下一个顶级子任务：存储层对接（将归一化后的 NewsItem 持久化写入 SQLite `news_items` 表，填充 `source_credibility` 字段）或实体标注阶段（从 NewsItem 提取公司/产品/技术实体，写入 `entities` 表）。

## 与 source-collection 的关系

- `source-collection` 阶段确立了 `RawDocument` 作为采集层统一输出结构，并在所有采集器（AkShare、Web、CopilotResearch）中实际使用；
- 本节点（定义原始文档结构）的工作是将这一结构从采集层局部类型**提升为流水线共享契约**，放入 `app/models/`，使采集层和归一化层都能引用同一定义，而不产生循环依赖或重复定义；
- `source-collection` 阶段遗留的采集器代码全部通过 shim 继续正常工作，未做任何功能性修改。

## 交接要求

- 上下文快用完时，先回写当前进度、修改文件、阻塞项和下一步，再切换新的子智能体。

