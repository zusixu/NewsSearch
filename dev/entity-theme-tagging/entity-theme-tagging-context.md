# entity-theme-tagging

## 关键文件

- `app/entity/__init__.py` — 包入口，导出 ThemeId / ThemeDefinition / THEME_TAXONOMY 及 EntityTypeId / EntityTypeDefinition / ENTITY_TYPE_TAXONOMY 与全部辅助函数，以及规则抽取层 Hit / RuleExtractor，以及模型抽取接口层 ModelExtractionRequest / ModelExtractionResponse / ModelExtractor，以及证据关联层 EvidenceSpan / EvidenceLink / EvidenceLinkError / build_evidence_links，以及标签化输出层 TaggedOutput / build_tagged_output
- `app/entity/themes.py` — 主题标签体系主数据（ThemeId 枚举 + ThemeDefinition 冻结 dataclass + THEME_TAXONOMY 字典）
- `app/entity/entity_types.py` — 实体类型体系主数据（EntityTypeId 枚举 + EntityTypeDefinition 冻结 dataclass + ENTITY_TYPE_TAXONOMY 字典）
- `app/entity/rules/__init__.py` — 规则抽取子包入口，导出 Hit、RuleExtractor
- `app/entity/rules/extractor.py` — Hit 冻结 dataclass + RuleExtractor 类（确定性规则抽取引擎）
- `app/entity/model_extractor.py` — 模型补充抽取接口（ModelExtractionRequest 冻结 dataclass + ModelExtractionResponse dataclass + ModelExtractor runtime_checkable Protocol）
- `app/entity/tagged_output.py` — 标签化输出模块（TaggedOutput frozen dataclass + build_tagged_output helper）
- `tests/test_tagged_output.py` — 标签化输出测试（37 个用例，全部通过）
- `tests/test_theme_taxonomy.py` — 主题体系完整性测试（84 个用例，全部通过）
- `tests/test_entity_types.py` — 实体类型体系完整性测试（59 个用例，全部通过）
- `tests/test_rule_extractor.py` — 规则抽取引擎测试（32 个用例，全部通过）
- `tests/test_model_extractor.py` — 模型抽取接口测试（42 个用例，全部通过）
- `app/entity/evidence.py` — 证据关联模块（EvidenceSpan / EvidenceLink frozen dataclass + EvidenceLinkError + build_evidence_links helper）
- `tests/test_evidence.py` — 证据关联测试（38 个用例，全部通过）

## 决策记录

- **主题数量：11 个**（9 个必选 + 2 个有 plan.md 依据的扩展）
  - 必选（来自 plan.md / context）：AI、基础模型、算力、内存、GPU、半导体、云服务、应用落地、供应链
  - 扩展：光模块（plan.md §信息链构建层显式列出）、存储（plan.md §数据采集层"算力、存储"并列）
- **标识符设计**：使用 `ThemeId(str, Enum)`，枚举值即 ID 字符串（如 `"ai"`），便于 JSON 序列化与数据库存储，跨版本稳定。
- **定义结构**：`ThemeDefinition` 是冻结 dataclass，包含 `id`、`label`（中文）、`label_en`、`description`、`keywords: Tuple[str, ...]`。
- **种子关键词**：仅作为规则抽取的初始词表，后续在 `app/entity/rules/` 中扩展，本模块不实现抽取逻辑。
- **辅助 API**：`get_theme`、`all_themes`、`theme_ids`、`find_themes_by_keyword`（大小写不敏感子串匹配）。
- **实体类型数量：6 种**（覆盖全部必选，无投机扩展）
  - 必选：COMPANY（公司）、PRODUCT（产品）、TECHNOLOGY（技术）、SUPPLY_CHAIN_ROLE（供应链角色）、REGION（地区）、POLICY_BODY（政策主体）
  - **产品/技术拆分决策**：PRODUCT 指具体商业型号（H100、DGX），TECHNOLOGY 指底层工艺/架构（CoWoS、Transformer、HBM），二者在信息链中作为不同类型节点连接供需与创新关系，拆分有利于精确建模，且有上下文建议依据。
- **EntityTypeDefinition 字段**：与 ThemeDefinition 结构平行；`example_mentions` 替代 `keywords`，语义上是"该类型的典型提及示例"而非"检索触发词"，更准确反映实体识别场景。
- **实体类型辅助 API**：`get_entity_type`、`all_entity_types`、`entity_type_ids`、`find_types_by_mention`（大小写不敏感子串匹配）。
- **证据关联模块放置**：`app/entity/evidence.py`（顶层，与 `rules/` 和 `model_extractor.py` 平级）。理由：证据关联是独立的横切关注点，不属于规则层也不属于模型层，与两者并列放置职责最清晰。
- **EvidenceSpan 字段设计**：`snippet`（命中原文）、`context_before` / `context_after`（上下文窗口，可配置，默认 50 字符）、`start` / `end`（偏移量，与 Hit 对齐）。snippet 冗余存储是为了让消费方无需再切片原文。
- **EvidenceLink 字段设计**：`hit`（原始 Hit 对象，直接引用，不拷贝）、`span`（EvidenceSpan）。保留 Hit 完整身份确保节点 6 能访问 kind / label_id / matched_seed 等全部字段。
- **不可变性**：EvidenceSpan 和 EvidenceLink 均为 frozen dataclass，与 Hit 风格一致。
- **偏移验证**：统一在 `_validate_offsets()` 中执行，任何非法偏移（负值、越界、end≤start）抛出 `EvidenceLinkError`（继承 ValueError），绝不静默忽略。
- **通用性**：`build_evidence_links` 对 `kind="theme"` 和 `kind="entity_type"` 的 Hit 均有效，节点 6 可统一调用，无需区分来源。
- **context_window 参数**：默认 50，传 0 时上下文为空串，负数抛出 ValueError，上下边界自动截断到文本边界。
  - 放置位置：`app/entity/model_extractor.py`（顶层，与 `rules/` 平级），而非 `rules/` 子包内。理由：规则抽取是确定性管道，模型抽取是不确定性外部调用，两者在语义上属于不同层，分离保持模块职责清晰。
  - `ModelExtractionRequest` 使用 **frozen dataclass**，与 `Hit` 保持一致，保证不可变传递。
  - `ModelExtractionResponse` 使用 **普通 dataclass**（非 frozen），允许调用方在后处理阶段追加 metadata（如 token 用量），更灵活。
  - `ModelExtractor` 使用 **`typing.Protocol` + `@runtime_checkable`**（非 ABC），支持结构子类型（无需继承），便于测试替身和依赖注入，同时支持 `isinstance` 检查。
  - 响应中的命中单元类型：直接复用规则层 `Hit`（`list[Hit]`），不引入新结构，保证节点 5 证据关联可以统一处理两层结果。
  - 来源字段：`provider`（服务商标识）+ `model`（模型版本）为必填，`notes`（自由备注）+ `error`（错误描述）+ `metadata: Dict[str, Any]`（扩展字典）为可选，满足可追溯性要求且不过度设计。
  - `rule_hits`（前置规则命中）+ `context_hint`（行业上下文）作为请求可选字段，为未来实现提供上下文注入点，当前不强制使用。
  - 含 CJK 字符的种子词（如"人工智能"、"SK 海力士"）→ 大小写不敏感子串匹配（非重叠）。CJK 无词边界，直接 `str.find()` 即可。
  - 纯 ASCII / 数字种子词（如 `AI`、`GPU`、`LLM`、`3nm`）→ 正则 `\b…\b` 词边界匹配（`re.IGNORECASE`）。防止短 token 在无关词内误命中（`AI` 不触发 `PAID`、`BRAIN`）。
  - 理由：确定性优先，无模糊逻辑；词边界规则对英文文本广泛适用且行为可预测。
- **Hit 结构**：`matched_text`、`start`（inclusive）、`end`（exclusive）、`matched_seed`、`kind`（"theme" | "entity_type"）、`label_id`（ThemeId/EntityTypeId 值字符串）。字段足以支撑后续证据关联（节点 5）和输出结构（节点 6），不做预期性扩展。
- **输出排序**：按 `(start, end, label_id)` 升序，保证确定性；相同位置相同标签去重。

## 当前进度

- ✅ `app/entity/themes.py` 已创建，定义 11 个主题，结构通过全量测试。
- ✅ `app/entity/__init__.py` 已更新，导出完整公开 API（主题 + 实体类型 + 规则抽取层）。
- ✅ `tests/test_theme_taxonomy.py` 已创建，覆盖唯一性、必选分类存在性、结构合法性、冻结不可变、查询行为（84 用例全通过）。
- ✅ `app/entity/entity_types.py` 已创建，定义 6 种实体类型（COMPANY / PRODUCT / TECHNOLOGY / SUPPLY_CHAIN_ROLE / REGION / POLICY_BODY），结构与 themes.py 平行。
- ✅ `tests/test_entity_types.py` 已创建，覆盖唯一性、必选类型存在性、产品/技术拆分、结构合法性、冻结不可变、查询行为、ID 字符串值稳定性（59 用例全通过）。
- ✅ `app/entity/rules/__init__.py` + `app/entity/rules/extractor.py` 已创建，实现 Hit dataclass + RuleExtractor 确定性规则抽取器（CJK 子串 / ASCII 词边界双路径）。
- ✅ `tests/test_rule_extractor.py` 已创建，覆盖中文命中、英文大小写不敏感命中、短 ASCII 假阳性规避、实体类型命中、排序去重、边界场景、导入导出接口（32 用例全通过）。

- ✅ `app/entity/model_extractor.py` 已创建，定义 ModelExtractionRequest（frozen dataclass）、ModelExtractionResponse（dataclass）、ModelExtractor（runtime_checkable Protocol），无任何真实模型调用。
- ✅ `app/entity/__init__.py` 已更新，新增导出三个模型抽取接口符号。
- ✅ `tests/test_model_extractor.py` 已创建，覆盖请求/响应构造、字段默认值与不可变性、Hit 兼容性（含规则层直通场景）、Protocol 合规性（minimal/rich/error/duck-typing fake 实现）、导入导出接口（42 用例全通过）。

- ✅ `app/entity/evidence.py` 已创建，定义 EvidenceSpan / EvidenceLink（frozen dataclass）、EvidenceLinkError、build_evidence_links helper；偏移验证严格，context_window 可配置（默认 50）。
- ✅ `app/entity/__init__.py` 已更新，新增导出四个证据关联符号（EvidenceSpan / EvidenceLink / EvidenceLinkError / build_evidence_links）。
- ✅ `tests/test_evidence.py` 已创建，38 个用例全部通过，覆盖：合法创建、snippet/context 行为、非法偏移显式拒绝、Hit 身份保留、空输入、导入导出接口。

- ✅ `app/entity/tagged_output.py` 已创建，定义 TaggedOutput（frozen dataclass：event / text / theme_ids / entity_type_ids / evidence_links）+ build_tagged_output helper；theme_ids / entity_type_ids 去重并升序排列，evidence_links 按 (start, end, label_id) 升序排列，全字段不可变 tuple。
- ✅ `app/entity/__init__.py` 已更新，新增导出 TaggedOutput / build_tagged_output。
- ✅ `tests/test_tagged_output.py` 已创建，37 个用例全部通过，覆盖：基本构建、排序去重确定性、证据关联排序、EventDraft 集成、空命中场景、frozen 不可变性、RuleExtractor 端到端流程、导入导出接口。
- ✅ 独立验证子智能体已完成第六节点验收：`tests/test_tagged_output.py` 37/37 通过；相关既有模块回归测试通过。
- ✅ 本地复核命令：
  - `conda run -n quant pytest tests/test_theme_taxonomy.py tests/test_entity_types.py tests/test_rule_extractor.py tests/test_model_extractor.py tests/test_evidence.py tests/test_tagged_output.py tests/test_raw_document.py tests/test_news_item.py tests/test_event_draft.py tests/test_url_dedup.py tests/test_text_dedup.py tests/test_time_norm.py tests/test_source_credibility.py -q`
  - 实际结果：**635/635 通过**

**entity-theme-tagging 子任务全部完成（共 6/6 项）。**

## 下一步

- entity-theme-tagging 已全部完成，建议推进下一顶层子任务：**信息链构建层（information-chain construction）**。

## 交接要求

- 上下文快用完时，先回写当前进度、修改文件、阻塞项和下一步，再切换新的子智能体。

