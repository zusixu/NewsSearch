# a-share-mapping

## 关键文件

- `app/mapping/schema.py` - A 股映射数据结构定义
- `app/mapping/industry_chain.py` - AI 产业链到 A 股环节映射规则
- `app/mapping/engine.py` - A 股映射引擎（转换规则实现）
- `app/mapping/report.py` - 日报输出模块
- `app/mapping/__init__.py` - 模块导出
- `tests/test_a_share_mapping_schema.py` - 数据结构测试
- `tests/test_industry_chain.py` - 产业链映射测试
- `tests/test_mapping_engine.py` - 映射引擎测试
- `tests/test_mapping_score.py` - 评分引擎测试
- `tests/test_mapping_evidence.py` - 旁证收集测试
- `tests/test_mapping_report.py` - 日报输出测试

## 决策记录

- 默认以 A 股映射为主。
- 港股/美股公司更多用于技术和产业验证。
- 输出需要覆盖行业/板块、候选标的池、具体个股三层。
- 所有映射结论需要带强弱分级/置信度分级。
- 使用 frozen dataclass 保证不可变性，可安全哈希/缓存/并发读取。
- 产业链采用三段式结构：上游（基础设施）/中游（技术与模型）/下游（应用落地）。
- 日报输出同时支持 Markdown（人工阅读）和 JSON（程序处理）两种格式。
- Markdown 格式注重可读性，包含表格、列表等元素；JSON 格式注重完整性，包含所有数据。

## 数据结构设计

### ConfidenceLevel（置信度分级）
- `HIGH` - 强信号，高置信度
- `MEDIUM` - 中等信号，部分证据支持
- `LOW` - 弱信号，间接证据或推测

### 三层映射结构
1. **SectorMapping** - 行业/板块与产业链环节映射
   - sector_name, chain_segment, confidence, rationale, theme_ids
2. **StockPoolMapping** - 候选标的池映射
   - pool_name, criteria, confidence, rationale, sector_name
3. **IndividualStockMapping** - 具体个股映射
   - stock_code, stock_name, confidence, rationale, impact_direction, pool_name, notes
4. **AStockMapping** - 完整的 A 股映射结构
   - chain_id, sector_mappings, stock_pool_mappings, individual_stock_mappings, overall_confidence, summary, generated_at

### 产业链结构
1. **IndustryChainPosition** - 产业链位置枚举：上游/中游/下游/全产业链
2. **IndustryChainNode** - 产业链节点：包含主题关联、A 股板块、候选标的、置信度、理由
3. **IndustryChainMap** - 完整产业链映射：提供按主题、位置查询的方法

### 映射引擎设计
1. **AShareMappingEngine** - A 股映射引擎
   - `map_tagged_output()` - 从 TaggedOutput 映射到 AStockMapping
   - `map_information_chain()` - 从 InformationChain 映射到 AStockMapping
   - `map_multiple_chains()` - 批量映射多条信息链
2. **MappingResult** - 单次映射结果结构，包含映射与元数据
3. **便捷函数** - `create_mapping_engine()` 和 `map_chain_to_a_share()`

### 映射流程
1. **主题匹配** - 从信息链中提取主题 ID
2. **产业链节点查询** - 根据主题 ID 查找相关产业链节点
3. **板块映射构建** - 构建 SectorMapping 列表
4. **标的池映射构建** - 构建 StockPoolMapping 列表
5. **个股映射构建** - 构建 IndividualStockMapping 列表（限制最多 10 个）
6. **置信度计算** - 根据板块映射计算整体置信度
7. **摘要构建** - 生成 A 股视角摘要
8. **结果返回** - 返回完整的 AStockMapping 结构

## 产业链节点覆盖

### 上游（基础设施层）
- 算力 - 数据中心、算力集群
- 存储 - NAND Flash、SSD
- 内存 - HBM、DRAM
- GPU / AI 芯片
- 半导体 - 设计/制造/封测/设备/材料
- 光模块 - 800G/1.6T 高速光互联
- 供应链 - PCB/散热/电源/服务器

### 中游（技术与模型层）
- 基础模型 - 大模型研发厂商
- 云服务 - 公有云/私有云厂商

### 下游（应用层）
- AI 应用 - AIGC/智能体/自动驾驶/垂直行业应用
- 人工智能 - 全产业链覆盖

## 当前进度

- ✅ 已完成节点 1：定义 A 股映射目标结构（28 个测试通过）
- ✅ 已完成节点 2：整理产业链环节映射（29 个测试通过）
- ✅ 已完成节点 3：建立链路到 A 股方向的转换规则（14 个测试通过）
- ✅ 已完成节点 4：增加 A 股可映射性评分（16 个测试通过）
- ✅ 已完成节点 5：设计旁证引用方式（18 个测试通过）
- ✅ 已完成节点 6：输出到日报字段（22 个测试通过）
- 全量测试通过（1544/1544）

---

## 可映射性评分设计决策

### 评分维度（5个）

1. **主题匹配度（theme_match_score）**：
   - 基于信息链主题与产业链节点的匹配程度
   - 匹配主题数量越多，得分越高
   - 权重：30%

2. **产业链清晰度（chain_clarity_score）**：
   - 基于产业链环节定位的明确程度
   - 覆盖上中下游多个环节的得分更高
   - 权重：25%

3. **置信度加权（confidence_weighted_score）**：
   - 基于映射结果的置信度等级
   - HIGH（100分）> MEDIUM（65分）> LOW（30分）
   - 权重：25%

4. **时效性（timeliness_score）**：
   - 目前默认 80 分
   - 后续可扩展为基于新闻时间与当前时间的差值计算
   - 权重：10%

5. **覆盖度（coverage_score）**：
   - 基于三层映射（板块/标的池/个股）的完整程度
   - 三层都有且个股数量多的得分更高
   - 权重：10%

### 评分等级

- **excellent（优秀）**：≥ 80 分
- **good（良好）**：≥ 60 分
- **fair（一般）**：≥ 40 分
- **poor（较差）**：< 40 分

### 数据结构

- **MappingScoreDimensions**：封装 5 个维度得分
- **AShareMappingScore**：完整评分结果，包含维度得分、总体评分、等级、理由和时间戳
- **ScoringResult**：映射与评分的组合结果

### 评分引擎

- **MappingScoringEngine**：核心评分引擎
  - `score_mapping()`：为现有 AStockMapping 计算评分
  - `score_chain()`：为 InformationChain 同时生成映射和评分
  - `score_multiple_chains()`：批量评分多条信息链

### 便捷函数

- `create_scoring_engine()`：创建默认配置的评分引擎
- `score_chain()`：为单个信息链生成映射和评分
- `score_mapping()`：为现有映射计算评分

## 旁证引用方式设计决策

### 数据结构
- **EvidenceSourceReference**：证据来源引用
  - 包含 chain_id、node_position、news_item_id、source_name、published_at
  - 支持追溯到原始信息链节点和新闻来源
- **EvidenceSnippetReference**：证据片段引用
  - 包含 snippet（命中文本）、context_before/context_after（上下文）、start/end（偏移量）
  - 可选包含 label_id 和 label_kind（theme/entity_type）
- **MappingEvidence**：映射旁证关联
  - mapping_type：sector/stock_pool/individual_stock
  - mapping_identifier：对应板块名/标的池名/股票代码
  - source_reference：关联的来源引用
  - snippet_references：关联的片段引用列表
  - rationale：旁证说明
- **AShareMappingWithEvidence**：带旁证的完整映射
  - 包含 AShareMapping 和 MappingEvidence 列表
  - 提供便捷方法：get_evidences_for_sector、get_evidences_for_stock_pool、get_evidences_for_stock

### 收集器设计
- **MappingEvidenceCollector**：旁证收集器
  - 支持从单个 TaggedOutput 或整个 InformationChain 收集证据
  - 自动从 evidence_links 中提取匹配的片段引用
  - 自动从 source_items 中提取来源元数据
  - 提供便捷函数 map_and_collect_evidence 同时完成映射和证据收集

### 设计原则
- 保持向后兼容：AStockMapping 结构不变，新增组合结构 AShareMappingWithEvidence
- 完整可追溯：既可以追溯到信息链/新闻来源，也可以定位到具体文本片段
- 灵活关联：支持板块、标的池、个股三种映射类型的证据关联
- 使用 frozen dataclass：保持与现有代码风格一致

## 日报输出设计决策

### 数据结构

1. **DailyReportHeader**：日报头部信息
   - report_date：报告日期（YYYY-MM-DD）
   - report_batch：报告批次（pre-market/midday）
   - generated_at：生成时间（ISO-8601 UTC）
   - prompt_profile：使用的 Prompt Profile 名称（可选）
   - prompt_version：使用的 Prompt Profile 版本（可选）

2. **DailyReportChainEntry**：单条信息链的日报条目
   - chain_id：信息链 ID
   - rank：排名
   - title：标题
   - summary：摘要
   - confidence：置信度
   - a_share_mapping：A 股映射结果
   - a_share_score：可映射性评分（可选）
   - with_evidence：旁证引用（可选）

3. **DailyReport**：完整日报
   - header：头部信息
   - top_chains：Top N 信息链条目列表
   - summary：日报摘要

### Markdown 报告生成

**设计原则**：
- 简洁易读：采用层次化结构（标题、列表、表格）
- 关键信息突出：将高置信度、高评分的映射结果放在前面
- 完整可追溯：包含旁证引用和来源信息

**结构**：
1. **头部**：报告标题、批次信息、生成时间
2. **今日概览**：总摘要、Top 10 摘要表格（排名、标题、置信度、可映射性等级）
3. **Top 10 详情**：每条信息链的详细信息
   - 摘要
   - A 股映射（行业/板块、标的池、个股）
   - 可映射性评分详情
   - 旁证引用
4. **底部**：声明和备注

### JSON 报告生成

**设计原则**：
- 完整准确：包含所有数据字段
- 结构化清晰：方便程序解析和二次处理
- 可扩展：预留可选字段和扩展空间

**结构**：
与数据结构完全对应，以 JSON 格式序列化，确保所有信息完整保留。

### DailyReportBuilder

提供一体化的构建和生成能力：
- `build()`：从信息链条目构建 DailyReport
- `to_markdown()`：生成 Markdown 报告
- `to_json()`：生成 JSON 报告
- `to_json_dict()`：生成 Python 字典格式

### 便捷函数

- `create_report_builder()`：创建默认配置的日报构建器
- `generate_markdown_report()`：便捷函数，直接从 DailyReport 生成 Markdown
- `generate_json_report()`：便捷函数，直接从 DailyReport 生成 JSON

### 日报内容示例

Markdown 报告包含：
- 清晰的表格展示板块、标的池、个股映射
- 置信度和评分等级的直观表示
- 旁证引用的简洁展示（限制数量避免冗长）

JSON 报告包含：
- 完整的三层映射结构
- 评分维度详情
- 完整的旁证引用信息
