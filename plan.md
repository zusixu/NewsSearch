# 每日 AI 投资新闻挖掘功能开发计划

## 问题与目标

在本地 Windows 环境中开发一个可每日自动运行的新闻挖掘系统，围绕人工智能及其上下游供应链持续收集信息，结合 Copilot 大模型分析能力与 web-access / AkShare 等渠道，输出**每日最值得关注的 10 条信息链**，用于发现潜在投资线索。

当前约束已确认：
- 提供给后续 AI 继续开发的方案文件固定使用当前目录下的 `plan.md`；
- 每日结果的投资映射以 **A 股** 为主，港股/美股仅作为辅助背景信息，不作为首要输出目标。

最终能力应覆盖：
- 每日自动执行；
- 采集 AI、本体模型、算力、存储、半导体、云服务、终端应用、供应链等相关新闻；
- 对资讯去重、聚合、串联成“事件链/逻辑链”；
- 结合市场与产业上下游关系给出投资视角；
- 输出可供后续 AI 和人工复核的结构化日报。

## 当前状态分析

- 当前工作目录 `D:\project\mm` 未发现现有项目文件，可视为**绿地项目**。
- 当前代码库中未发现：
  - 现成的 Python/Node 项目骨架；
  - 调度脚本或任务计划配置；
  - 数据存储、分析、测试或文档文件。
- 用户已说明：
  - `conda` 的 `quant` 环境已配置 AkShare；
  - 需要本地每日自动运行；
  - 希望借助 Copilot 大模型分析能力与 web-access skill；
  - 后续需要在当前目录保留一份完整开发方案给其他 AI 继续开发。

## 外部参考资料

为方便后续开发智能体快速查阅，以下外部资料视为本项目实现过程中的核心参考入口：

- **AkShare 文档**：`https://akshare.akfamily.xyz/`
- **AkShare GitHub 项目**：`https://github.com/akfamily/akshare`

使用 AkShare 相关接口前，应优先查阅上述文档与仓库说明，确认函数名、参数、返回结构和适用范围，而不是凭记忆猜测。

## 建议方案总览

建议采用**“本地采集 + 结构化归一化 + 信息链构建 + LLM 投资分析 + 定时调度输出”**的分层架构，并将模型调用做成可替换适配层，避免后续受限于单一调用方式。

### 1. 运行与调度层

- 主实现语言：**Python**（优先复用 `quant` 环境与 AkShare）。
- 提供：
  - 单次执行入口：`python -m app.main`
  - Windows Task Scheduler 注册脚本
  - 本地 `.env + YAML` 配置
- 调度策略：
  - 每日固定时段拉取、分析、产出；
  - 支持补跑指定日期；
  - 支持 dry-run / 仅采集 / 仅分析模式。

### 2. 数据采集层

按“确定性优先，浏览器探索补充”的原则设计多源采集：

- **AkShare 适配器**
  - 采集可用的财经/新闻/公告/产业相关数据；
  - 补充市场表现、板块/个股上下文。
- **公开网络采集适配器**
  - 官方新闻页、博客、RSS、公告页、公司新闻中心、研究机构页面。
- **Copilot + web-access 深度检索适配器**
  - 用于补足静态源找不到、需要跨站串联、或需要浏览器环境判断真伪的场景；
  - 是每日自动任务中的**强制参与组件**，不是可选增强项；
  - 应作为标准采集流水线的一部分接入，而不是只在个别场景下临时启用。
- 所有来源统一落为标准化 `RawDocument` / `NewsItem` 结构。

AkShare 开发时的优先参考资料：
- 文档：`https://akshare.akfamily.xyz/`
- 仓库：`https://github.com/akfamily/akshare`

### 3. 数据归一化与存储层

- 使用 **SQLite** 存储：
  - 原始抓取结果；
  - 标准化资讯；
  - 实体（公司/产品/技术/供应链节点）；
  - 信息链与评分结果；
  - 每日运行日志。
- 增加：
  - URL 指纹与文本哈希去重；
  - 时间标准化；
  - 来源可信度等级；
  - 抓取缓存与失败重试记录。

### 4. 信息链构建层

这是本需求的核心能力，目标不是“列 10 条新闻”，而是“列 10 条值得跟踪的信息链”。

计划构建以下处理流程：

1. **主题识别**：识别 AI / 算力 / 内存 / GPU / 光模块 / 云厂商 / 芯片 / 应用落地等主题。
2. **实体抽取**：抽取公司、产品、技术名词、供应链角色、地区、政策主体。
3. **事件抽象**：把单篇资讯归纳为事件，如“Google 降低模型内存占用”“HBM 需求提升”“某厂扩产”。
4. **关系连接**：
   - 因果：A 导致 B；
   - 上下游：A 变化影响 B/C；
   - 时间延续：同一事件多日发酵；
   - 市场映射：事件影响到哪些板块/公司类型。
5. **链路生成**：输出完整逻辑链，例如：
   - 技术突破/成本变化 → 基础设施需求变化 → 供应链受益/受损环节 → 潜在投资关注点。

### 5. LLM 分析层

构建 `analysis_adapter`，将模型调用与业务逻辑解耦。

这一层必须保留**人工可介入的 prompt 调整接口**，避免分析逻辑被硬编码在程序里。建议：
- 将系统 prompt、任务 prompt、排序 prompt 拆成独立模板文件；
- 支持你直接修改本地 prompt 文件后重新运行；
- 支持通过配置指定启用哪一版 prompt；
- 在日报结果中记录本次运行使用的 prompt 版本，便于回溯。

每条候选信息链的分析输出至少包括：
- 事件摘要；
- 关键证据来源；
- 上下游逻辑链；
- 潜在受益/受损方向；
- 为什么值得关注；
- 新颖度/重要性/可信度评分；
- 是否进入 Top 10。

建议把模型任务拆成三类：
- **摘要归纳**：把多篇材料合并成单一事件；
- **链路推理**：补全上下游与因果关系；
- **投资排序**：按重要度、新颖度、可验证性排序。

建议同时提供一个简单的手动介入方式，例如：
- `app/analysis/prompts/` 存放各类 prompt 模板；
- `config/prompt_profiles/` 或 `.env` / YAML 中指定当前使用的 prompt profile；
- 命令行允许传入类似 `--prompt-profile aggressive-v1` 的参数，用于临时切换分析口径。

### 6. 日报输出层

每日输出至少两类产物：

- **Markdown 报告**
  - 便于阅读和交给后续 AI 二次加工；
- **JSON 结构化结果**
  - 便于后续做前端、回测、追踪或再次分析。

日报建议包含：
- 当日 Top 10 信息链；
- 每条链的证据链接；
- 产业链位置；
- 投资关注点（默认优先映射到 A 股相关板块、产业环节、潜在受益标的类型）；
- 风险与反证；
- 附录：候选但未入选的事件摘要。

### 7. 质量与运维

- 明确日志、失败重试、超时控制；
- 支持来源级禁用/启用；
- 支持 prompt / 规则版本化；
- 增加最小测试集：
  - 归一化测试；
  - 去重测试；
  - 信息链构建测试；
  - 报告生成测试。

## 推荐目录结构

若开始实现，建议采用如下结构：

```text
mm/
├── app/
│   ├── main.py
│   ├── config/
│   ├── collectors/
│   │   ├── akshare_collector.py
│   │   ├── web_collector.py
│   │   └── copilot_research_collector.py
│   ├── normalize/
│   ├── entity/
│   ├── chains/
│   ├── analysis/
│   │   ├── prompts/
│   │   └── adapters/
│   ├── ranking/
│   ├── reports/
│   ├── storage/
│   └── scheduler/
├── data/
│   ├── raw/
│   ├── db/
│   └── reports/
├── scripts/
│   ├── run_daily.ps1
│   ├── register_task.ps1
│   └── bootstrap.ps1
├── tests/
├── .env.example
└── docs/
```

## dev 开发进度监控结构

为支持后续持续开发与多轮交接，在项目根目录新增 `dev/` 目录，作为**任务拆解、上下文沉淀、执行清单**的主工作区。

建议结构如下：

```text
mm/
├── dev/
│   ├── project-bootstrap/
│   │   ├── project-bootstrap-plan.md
│   │   ├── project-bootstrap-context.md
│   │   └── project-bootstrap-task.md
│   ├── source-collection/
│   ├── normalization-pipeline/
│   ├── entity-theme-tagging/
│   ├── information-chain/
│   ├── a-share-mapping/
│   ├── llm-analysis/
│   ├── reporting-output/
│   ├── scheduler-automation/
│   └── qa-observability/
```

每个子任务目录固定包含三类文件：

- `任务名-plan.md`：任务目标、实现方式、边界与分阶段做法；
- `任务名-context.md`：关键文件、依赖关系、接口约束、决策记录；
- `任务名-task.md`：可勾选 checklist，记录执行状态、阻塞项和验收点。

命名规则已确认：
- `dev/` 下的子任务目录统一使用**英文 kebab-case**；
- 三个 markdown 文件也统一使用相同的英文 kebab-case 任务名作为前缀；
- 例如 `information-chain/information-chain-plan.md`。

## 新增执行硬约束：任务清单即时更新与上下文续接

在整个开发过程中，所有开发智能体都必须严格遵守以下规则：

1. **每完成一步，立刻更新对应任务清单**
   - 只要完成了一个 checklist 项，必须立即更新对应的 `任务名-task.md`；
   - 如果是部分完成，也要写明当前完成到哪一步，而不是等一整个阶段结束后再补记；
   - 如果一个动作同时影响多个子任务，需要同步更新多个任务目录下的清单。

2. **上下文快用完时，先写交接，再切换智能体**
   - 一旦判断当前上下文即将不足以继续稳定工作，必须立刻停止继续实现；
   - 先把已完成进度、当前状态、阻塞信息、下一步动作写入对应的 `任务名-context.md`；
   - 然后再开启新的子智能体，并要求其先阅读相关 `plan.md`、`context.md`、`task.md` 再继续。

3. **禁止无文档交接**
   - 不允许在未更新文档的情况下直接切换子智能体；
   - 不允许把关键进度只留在临时上下文里而不回写到文件。

4. **交接最小内容**
   - 当前已经完成了什么；
   - 当前修改影响了哪些文件；
   - 还有什么未完成；
   - 下一步最推荐先做什么；
   - 是否存在需要向用户确认的问题。

## 新增实施约束：Prompt 可人工干预

- AI 分析部分必须允许你手动调整 prompt，而不是只能改代码；
- prompt 应以独立文件方式管理，并支持多版本并存；
- 每次运行应能追踪使用了哪套 prompt 模板；
- 当分析效果不理想时，优先通过 prompt profile 调整，而不是直接修改主流程代码。

后续开发过程中，需要把这些文件作为**长期维护资产**：
- 开工前先读相关子任务的三份文档；
- 设计变化后同步更新 `*-context.md`；
- 范围变化或实现策略变化后同步更新 `*-plan.md`；
- 完成或阻塞时更新 `*-task.md`；
- 不确定问题及时向用户确认，而不是在文档中擅自定死。

## 子任务拆解

建议将当前总体计划拆成以下可独立推进的子任务：

### 1. project-bootstrap
- 目标：初始化 Python 项目骨架、配置体系、日志、SQLite、CLI 入口和 `quant` 环境约定。
- 产出：最小可运行项目结构与基础运行命令。

### 2. source-collection
- 目标：实现 AkShare 采集器、公开网页采集器，并为 Copilot/web-access 研究适配器预留统一接口。
- 产出：标准化原始采集记录与缓存机制。

### 3. normalization-pipeline
- 目标：实现去重、时间标准化、来源可信度分级、原始文档到事件草稿的转换。
- 产出：统一 `RawDocument` / `NewsItem` / `EventDraft` 流程。

### 4. entity-theme-tagging
- 目标：抽取 AI 主题、公司、产品、技术、供应链角色，并打上后续分析需要的主题标签。
- 产出：可用于链路构建和 A 股映射的实体与标签层。

### 5. information-chain
- 目标：把离散事件连接成带因果、时序、上下游关系的信息链。
- 产出：链路生成规则、候选链对象、链路证据集合。

### 6. a-share-mapping
- 目标：把事件链映射到 A 股板块、产业环节、公司类型或候选标的池。
- 产出：A 股优先的投资映射层与加分规则。

### 7. llm-analysis
- 目标：接入 GitHub Models / 可编程 API，完成摘要归纳、链路补全、投资排序与解释生成，并保留人工可修改的 prompt 接口。
- 产出：统一分析适配器、prompt 模板资产、prompt profile 切换机制、结构化分析结果。

### 8. reporting-output
- 目标：生成每日 Top 10 Markdown/JSON 报告，沉淀证据、逻辑链、A 股关注点和风险说明。
- 产出：日报生成器与历史归档结构。

### 9. scheduler-automation
- 目标：实现本地每日自动运行、补跑、日志落盘、失败重试和 Windows Task Scheduler 集成。
- 产出：自动化脚本和调度注册能力。

### 10. qa-observability
- 目标：补足测试、运行日志、异常跟踪、版本记录与人工校验入口。
- 产出：基础测试集、日志规范、问题回溯能力。

## 分阶段实施计划

### Phase 1：项目骨架与配置
- 初始化 Python 项目结构；
- 固化配置加载、日志、SQLite、基础 CLI；
- 增加 `quant` 环境启动约定。

### Phase 2：采集适配器
- 先实现 AkShare 与公开网页源；
- 预留 Copilot/web-access 研究适配器接口；
- 打通原始数据入库与缓存。

### Phase 3：归一化与事件抽象
- 去重、时间标准化、来源分级；
- 事件摘要抽取；
- 建立实体与主题标签。

### Phase 4：信息链构建与排序
- 建立上下游映射规则；
- 接入 LLM 推理补链；
- 形成候选链评分与 Top 10 排序。

### Phase 5：日报与自动运行
- 输出 Markdown + JSON；
- 提供每日自动运行脚本；
- 增加补跑、失败告警、历史归档。

### Phase 6：交接文档
- 直接维护当前目录下的 `plan.md`，作为供后续 AI 继续开发的详细实施文档；
- 记录模块边界、输入输出、运行方式、测试命令。

### Phase 7：dev 任务监控资产
- 创建 `dev/` 与各子任务目录；
- 为每个子任务初始化 `*-plan.md` / `*-context.md` / `*-task.md`；
- 在后续开发中持续维护这些文件，作为任务执行与交接来源。

## 风险与关键决策

已确认优先采用：**GitHub Models / 可编程 API** 作为无人值守的 Copilot 大模型调用方案。

因此实现时应：
- 先把 **采集 / 信息链构建 / 模型调用** 明确拆层，避免后期重构成本；
- 将模型调用集中在 `analysis_adapter` 中，便于后续替换模型、鉴权方式或 prompt 策略；
- 保留 web-access 作为增强型研究能力，而不是让主流程直接耦合到交互式浏览器链路。

## 已确认实施约束

- 当前目录中的 `plan.md` 是后续 AI 开发的主参考文档，不再额外拆分新的方案文件；
- 每日输出以 A 股投资映射为主：
  - 优先关联 A 股板块、产业链环节、受益方向与标的类型；
  - 港股/美股公司可作为产业验证、技术源头或映射证据；
  - 排序与推荐解释中，A 股可映射性应作为重要加分项之一。

## 计划审查结论

本轮已对 `plan.md` 与 `dev/` 目录下的任务文档进行一致性检查。

当前结论：
- **未发现明显自相矛盾的计划**；
- 主线结构清晰：采集 → 归一化 → 信息链 → A 股映射 → LLM 分析 → 报告 → 调度；
- dev 子任务拆解与总计划基本一致；
- 执行纪律、交接规则、Prompt 可人工干预、AkShare 参考入口都已落到文档中。

当前仍存在的主要未定点：
- 当前没有新的架构级未定点；剩余实现细节可在执行中持续写回 `dev/` 文档。

处理原则：
- 遇到会影响架构边界或开发顺序的不确定项，必须先向用户确认；
- 其余实现细节可在不违背当前约束的前提下继续推进，并持续写回 `dev/` 文档。

已新增确认：
- 自动化每日运行时，`web-access` **每次都要调用**，作为每日主流程的固定组成部分；
- 因此采集架构必须稳定支持：AkShare / 静态网页源 / 自动化 `web-access` research collector 三类来源；
- `web-access` 不是“允许时调用”，而是“默认每次执行都参与”。
- A 股映射结果默认输出三层：
  - 行业/板块与产业链环节；
  - 候选标的池；
  - 具体个股结论；
  - 但所有结论都必须带**强弱分级/置信度分级**，避免把弱信号写成强推荐。
- 自动运行默认每天两次：
  - **开盘前一小时**一次；
  - **下午两点**一次。

  这意味着调度层、日报命名、历史归档都应支持“同一天多批次运行”。
- Python 包管理与运行环境固定使用本地 `conda` 的 `quant` 环境；
- 配置文件最终格式固定为：
  - `.env`：存放密钥、令牌、环境变量类配置；
  - `YAML`：存放来源开关、prompt profile、调度参数、输出参数等业务配置。

## 最新开发进展（暂停点）

截至当前暂停点，已完成以下开发与文档回写：

- **project-bootstrap 已全部完成**
  - 已建立 Python 项目骨架、`python -m app.main` CLI 入口；
  - 已建立 `.env + YAML` 配置加载；
  - 已建立日志模块与 SQLite 初始化逻辑；
  - 已提供 `scripts/bootstrap.ps1`，可直接在 `quant` 环境中启动；
  - 已补齐 `README.md` 启动说明。

- **source-collection 已全部完成**
  - 已定义统一 collector 接口；
  - 已接入 AkShare 采集器（当前首批 provider：CCTV、Caixin）；
  - 已接入公开网页采集器（支持 RSS/Atom 与静态 HTML，来源可配置）；
  - 已定义 Copilot / web-access research collector 的 transport 契约；
  - 已将临时 dict 契约收敛为统一 `RawDocument`；
  - 已增加 `data/raw/` 文件系统缓存；
  - 已增加仅针对瞬时错误的通用重试机制。

- **当前测试状态**
  - 当前仓库共 **360** 个测试，全部通过。

## 恢复开发后的最新进展

- **normalization-pipeline 已全部完成**
  - 已完成 `RawDocument` 共享模型落位，作为采集层到归一化层的统一输入契约；
  - 已完成 `NewsItem` 共享模型定义，作为归一化阶段的标准资讯输出；
  - 已完成 `EventDraft` 共享模型定义，作为事件抽取阶段的中间输出；
  - 已完成基于规范化 URL 指纹的首轮去重模块；
  - 已完成基于 title + body 的文本哈希去重模块；
  - 已完成时间标准化模块，支持多种日期格式并把失败信息写入 `metadata["time_normalization"]`；
  - 已完成来源可信度分级模块，8 条有序规则（0–5 分），结果写入 `metadata["source_credibility"]`；
  - 已明确三段式链路：`RawDocument -> NewsItem -> EventDraft`，并保留端到端回溯引用。

- **当前专项测试状态**
  - `tests/test_raw_document.py`：**11/11** 通过；
  - `tests/test_news_item.py`：**29/29** 通过；
  - `tests/test_event_draft.py`：**37/37** 通过；
  - `tests/test_url_dedup.py`：**48/48** 通过；
  - `tests/test_text_dedup.py`：**51/51** 通过；
  - `tests/test_time_norm.py`：**87/87** 通过；
  - `tests/test_source_credibility.py`：**80/80** 通过；
  - 当前已完成的归一化阶段专项测试合计 **343/343** 通过。

- **下一步推荐执行点**
  - `normalization-pipeline` 全部七个 checklist 节点均已完成；
  - 推荐下一个顶级子任务：**entity-theme-tagging**（实体标注与主题标签）；
  - 或先做：**存储层对接**（将归一化后的 NewsItem 持久化写入 SQLite `news_items` 表，`source_credibility` 字段已在 schema 中预留）。

### 当前仍待补充但不阻塞继续开发的点

- WebCollector 首批来源名单（URL、type、provider 标签）尚未最终敲定；
- 采集频率与限流策略仍需在后续调度/运维阶段进一步收敛。

## entity-theme-tagging 完成（节点 6/6）

- **entity-theme-tagging 已全部完成**（共 6 个 checklist 节点，全部 ✅）
  - 已定义 11 个主题标签体系（ThemeId / ThemeDefinition / THEME_TAXONOMY）；
  - 已定义 6 种实体类型体系（EntityTypeId / EntityTypeDefinition / ENTITY_TYPE_TAXONOMY）；
  - 已实现确定性规则抽取引擎（Hit / RuleExtractor，CJK 子串 + ASCII 词边界双路径）；
  - 已定义模型补充抽取接口（ModelExtractionRequest / ModelExtractionResponse / ModelExtractor Protocol）；
  - 已实现证据关联层（EvidenceSpan / EvidenceLink / build_evidence_links）；
  - 已实现标签化结果输出层（TaggedOutput / build_tagged_output）。

- **entity-theme-tagging 专项测试状态**
  - `tests/test_theme_taxonomy.py`：**84/84** 通过；
  - `tests/test_entity_types.py`：**59/59** 通过；
  - `tests/test_rule_extractor.py`：**32/32** 通过；
  - `tests/test_model_extractor.py`：**42/42** 通过；
  - `tests/test_evidence.py`：**38/38** 通过；
  - `tests/test_tagged_output.py`：**37/37** 通过；
  - entity-theme-tagging 专项测试合计 **292/292** 通过。
  - 联合归一化阶段本地复核：**635/635** 通过。

- **下一步推荐执行点**
  - `entity-theme-tagging` 已全部完成；
  - 推荐下一个顶级子任务：**information-chain（信息链构建层）**，消费 `TaggedOutput` 将离散事件连接成带因果、时序、上下游关系的信息链。

## information-chain 完成（节点 7/7）

- **information-chain 已全部完成**
  - 已完成 `app/chains/chain.py`，定义 `ChainNode`、`InformationChain` 与 `build_chain`；
  - 已完成 `app/chains/relation_type.py`，定义 `RelationType`（因果 / 时间延续 / 上下游影响 / 同主题发酵）；
  - 已将 `ChainNode.relation_to_prev` 从字符串占位升级为 `RelationType | None`；
  - 已完成 `app/chains/same_topic_grouping.py`，基于共享 `theme_ids` 的传递闭包实现稳定同主题聚合；
  - 已完成 `app/chains/temporal_connection.py`，对现有链做稳定时序重排，并将相邻关系标记为 `RelationType.TEMPORAL`；
  - 已完成 `app/chains/upstream_downstream.py`，基于 `theme_ids` 的保守阶段映射实现上下游连接；
  - 已完成 `app/chains/candidate_generation.py`，将同主题聚合 → 时序连接 → 上下游连接串成候选链流水线；
  - 已完成 `app/chains/evidence_retention.py`，聚合每条链的 `NewsItem` 来源集合与 `EvidenceLink` 证据集合；
  - 已更新 `app/chains/__init__.py`，对外导出 `ChainNode`、`InformationChain`、`RelationType`、`build_chain`、`group_same_topic`、`apply_temporal_order`、`apply_upstream_downstream_order`、`generate_candidate_chains`、`ChainEvidenceBundle`、`collect_chain_evidence`、`collect_all_evidence`。

- **当前专项测试状态**
  - `tests/test_chain.py`：**39/39** 通过；
  - `tests/test_relation_type.py`：**40/40** 通过；
  - `tests/test_same_topic_grouping.py`：**36/36** 通过；
  - `tests/test_temporal_connection.py`：**36/36** 通过；
  - `tests/test_upstream_downstream.py`：**48/48** 通过；
  - `tests/test_candidate_generation.py`：**35/35** 通过；
  - `tests/test_evidence_retention.py`：**41/41** 通过；
  - information-chain 当前专项测试合计 **275/275** 通过；
  - 联合既有 entity + normalization 聚焦回归：**635/635** 通过。

- **下一步推荐执行点**
  - `information-chain` 已全部完成；
  - 推荐下一个顶级子任务：**llm-analysis**，在当前已成型的候选链与证据集合之上接入 prompt/profile、摘要归纳、链路解释与投资排序；
  - 继续保持“每完成一个 checklist 节点，立即单独拉起子智能体做验收”的执行纪律。

## llm-analysis 已完成（所有 7/7 节点已完成）

- **llm-analysis 已全部完成！**

  - ✅ 第 1 步：定义 analysis adapter 接口（frozen dataclass + Protocol），39 个测试全部通过。
  - ✅ 第 2 步：接入 GitHub Models（`GitHubModelsAdapter` + 可注入 `PromptRenderer` + 配置层），13 个测试全部通过。
  - ✅ 第 3 步：建立 prompt 模板目录。
    - 已完成 `FileSystemPromptRenderer`，默认从 `app/analysis/prompts/templates/` 加载模板；
    - 已为 `SUMMARY`、`CHAIN_COMPLETION`、`INVESTMENT_RANKING` 建立默认 JSON 模板；
  - ✅ 第 4 步：建立 prompt profile 机制。
    - 已在 `config/prompt_profiles/` 目录设计 YAML 格式的 profile 配置文件；
    - 已创建默认 profile `config/prompt_profiles/default.yaml`；
    - 已在 `app/analysis/prompts/profile.py` 建立 profile 读取与解析层；
    - `tests/test_prompt_profile.py`（21 个测试）。
  - ✅ 第 5 步：支持命令行切换 prompt profile。
    - 已在 `app/main.py` 中增加 `--prompt-profile` 参数；
    - 已更新所有模式的处理函数，支持 profile 配置的传递和显示。
  - ✅ 第 6 步：记录运行使用的 prompt 版本。
    - 已扩展 `run_logs`、`chain_scores` 表，新增 prompt profile 字段；
    - 已新增 `prompt_profiles` 表，用于完整归档 prompt profile；
    - 已新增 `RunLogStore`、`PromptProfileStore` 存储类；
    - `tests/test_prompt_version_tracking.py`（13 个测试）。
  - ✅ 第 7 步：输出结构化分析结果。
    - 已在 `app/analysis/engine.py` 中实现 `AnalysisEngine` 分析引擎；
    - 已实现 `DryRunAnalysisAdapter`，无需真实 LLM 的 dry-run 适配器；
    - 已实现完整流程：`TaggedOutput` → `InformationChain` → `AnalysisInput` → `AnalysisResponse`；
    - 已新增 `ChainScoreStore`、`InfoChainStore` 存储类；
    - 已更新 `app/main.py` 的 `run` 和 `analyze-only` 模式，调用分析引擎；
    - `tests/test_analysis_engine.py`（13 个测试）。

- **当前专项测试状态**
  - `tests/test_analysis_adapter_contracts.py`：39/39 通過；
  - `tests/test_github_models_adapter.py`：13/13 通過；
  - `tests/test_filesystem_prompt_renderer.py`：通过；
  - `tests/test_prompt_profile.py`：21/21 通过；
  - `tests/test_prompt_version_tracking.py`：13/13 通过；
  - `tests/test_analysis_engine.py`：13/13 通过；
  - 全量回归：`pytest tests\ -q` **1417/1417** 通过。

- **下一步推荐执行点**
  - llm-analysis 已全部完成；
  - a-share-mapping 已完成节点 1-3（定义结构、产业链映射、转换规则）；
  - 推荐继续完成 a-share-mapping 的剩余节点：可映射性评分、旁证引用、日报输出集成；
  - 或下一个：**reporting-output**（报告输出），生成每日 Top 10 Markdown/JSON 报告。

## a-share-mapping 已完成（所有 6/6 节点已完成）

- **a-share-mapping 已全部完成！**

  - ✅ 第 1 步：定义 A 股映射目标结构，28 个测试全部通过。
  - ✅ 第 2 步：整理产业链环节映射，29 个测试全部通过。
  - ✅ 第 3 步：建立链路到 A 股方向的转换规则，14 个测试全部通过。
  - ✅ 第 4 步：增加 A 股可映射性评分，16 个测试全部通过。
  - ✅ 第 5 步：设计旁证引用方式，18 个测试全部通过。
  - ✅ 第 6 步：输出到日报字段，22 个测试全部通过。

- **当前专项测试状态**
  - 测试数据结构：`tests/test_a_share_mapping_schema.py`，28/28 个测试通过。
  - 测试产业链映射：`tests/test_industry_chain.py`，29/29 个测试通过。
  - 测试映射引擎：`tests/test_mapping_engine.py`，14/14 个测试通过。
  - 测试评分引擎：`tests/test_mapping_score.py`，16/16 个测试通过。
  - 测试旁证收集：`tests/test_mapping_evidence.py`，18/18 个测试通过。
  - 测试日报输出：`tests/test_mapping_report.py`，22/22 个测试通过。
  - 全量回归测试：`pytest tests -q`，**1544/1544** 个测试通过。

- **a-share-mapping 完成内容**
  - 定义三层映射结构：行业/板块、候选标的池、具体个股。
  - 建立 AI 产业链与 A 股映射关系，覆盖 11 个主题。
  - 实现映射引擎，支持从 TaggedOutput 或 InformationChain 映射。
  - 实现评分引擎，5 个维度（主题匹配度、产业链清晰度、置信度加权、时效性、覆盖度），权重分别为 30%、25%、25%、10%、10%。
  - 实现旁证收集，支持证据来源引用和证据片段引用。
  - 实现日报输出，支持 Markdown（人工阅读）和 JSON（程序处理）两种格式。

- **关键文件**
  - 数据结构定义：`app/mapping/schema.py`
  - 产业链映射：`app/mapping/industry_chain.py`
  - 映射引擎：`app/mapping/engine.py`
  - 日报输出：`app/mapping/report.py`

- **下一步推荐执行点**
  - 推荐下一个顶级子任务：**reporting-output**（报告输出），将 llm-analysis 和 a-share-mapping 整合为完整的日报生成流程。

## reporting-output 已完成（所有 7/7 节点已完成）

- **reporting-output 已全部完成！**

  - ✅ 第 1 步：定义日报数据结构（DailyReport / DailyReportHeader / DailyReportChainEntry / RiskWarning），32 个测试全部通过。
  - ✅ 第 2 步：设计 Markdown 模板，实现 MarkdownReportGenerator，包含头部、总览、风险提示、Top 10 链详情、底部免责声明。
  - ✅ 第 3 步：设计 JSON schema，实现 JsonReportGenerator，输出完整结构化 JSON。
  - ✅ 第 4 步：输出 Top 10 信息链，基于 AnalysisResponse 中的 ranking 信息按排名顺序输出。
  - ✅ 第 5 步：输出 A 股映射字段，完整支持三层映射（行业/板块、候选标的池、具体个股）+ 可映射性评分 + 旁证引用。
  - ✅ 第 6 步：输出风险与反证字段，实现 RiskWarning 数据结构和自动风险提示生成（低置信度、低可映射性、全局免责声明）。
  - ✅ 第 7 步：建立历史归档结构，实现 ReportArchiveManager，支持按 YYYY/MM/DD 目录组织、文件命名规范（YYYYMMDD-pre-market.md / YYYYMMDD-midday.md）、按日期/批次过滤列表查询。

- **当前专项测试状态**
  - `tests/test_reports.py`：**32/32** 通过；
  - 全量回归测试：`pytest tests -q`，**1544/1544** 个测试通过。

- **reporting-output 完成内容**
  - 日报数据结构：DailyReport、DailyReportHeader、DailyReportChainEntry、RiskWarning
  - Markdown 生成器：完整的 Markdown 报告，包含表格、评分详情、旁证引用
  - JSON 生成器：完整结构化 JSON，支持序列化和反序列化
  - 日报构建器：DailyReportBuilder，从 AnalysisResponse + AStockMapping 构建完整日报
  - 归档管理器：ReportArchiveManager，按日期目录组织，支持保存和查询历史报告

- **关键文件**
  - 日报核心：`app/reports/core.py`
  - 报告模块入口：`app/reports/__init__.py`

- **下一步推荐执行点**
  - 推荐下一个顶级子任务：**scheduler-automation**（调度自动化），实现每日自动运行、Windows Task Scheduler 集成、补跑和重试。
  - 或：**qa-observability**（质量与可观测性），补足测试、运行日志、异常跟踪和人工校验入口。

## scheduler-automation 已完成（所有 6/6 节点已完成）

- **scheduler-automation 已全部完成！**

  - ✅ 第 1 步：建立日常运行脚本（`scripts/run_daily.ps1`），自动检测批次、conda quant 环境启动。
  - ✅ 第 2 步：建立计划任务注册脚本（`scripts/register_task.ps1`），注册 Windows Task Scheduler 两个任务（mm-pre-market 08:30、mm-midday 14:00），支持 -Unregister 卸载。
  - ✅ 第 3 步：支持补跑参数（`--Date YYYY-MM-DD`），在 `run_daily.ps1` 和 `bootstrap.ps1` 中均已支持。
  - ✅ 第 4 步：支持日志落盘，通过 `app/logger` JSON NDJSON 日志 + 每日轮转，`run_daily.ps1` 输出带时间戳的控制台日志。
  - ✅ 第 5 步：设计失败重试（`DailyScheduler` + `RetryPolicy`），支持可配置的最大重试次数、基础延迟、指数退避。
  - ✅ 第 6 步：编写使用说明（`bootstrap.ps1` / `run_daily.ps1` / `register_task.ps1` 均有完整 `.SYNOPSIS` / `.EXAMPLE`）。

- **当前专项测试状态**
  - `tests/test_scheduler.py`：**38/38** 通过；
  - 全量回归测试：`pytest tests -q`，**1614/1614** 个测试通过。

- **关键文件**
  - 调度核心：`app/scheduler/scheduler.py` — DailyScheduler / RetryPolicy / determine_batch / should_run_now / create_scheduler
  - 模块入口：`app/scheduler/__init__.py`
  - 运行脚本：`scripts/run_daily.ps1`
  - 注册脚本：`scripts/register_task.ps1`

## qa-observability 已完成（所有 7/7 节点已完成）

- **qa-observability 已全部完成！**

  - ✅ 第 1 步：建立最小测试结构 — `tests/` 目录下 42 个测试文件，覆盖所有核心模块。
  - ✅ 第 2 步：增加归一化测试 — test_raw_document (11), test_news_item (29), test_event_draft (37), test_url_dedup (48), test_text_dedup (51), test_time_norm (87), test_source_credibility (80) — 合计 343 个测试。
  - ✅ 第 3 步：增加信息链测试 — test_chain (39), test_relation_type (40), test_same_topic_grouping (36), test_temporal_connection (36), test_upstream_downstream (48), test_candidate_generation (35), test_evidence_retention (41) — 合计 275 个测试。
  - ✅ 第 4 步：增加报告生成测试 — test_reports (32), test_a_share_mapping_schema (28), test_mapping_report (22) 等。
  - ✅ 第 5 步：统一日志格式 — `app/logger/` 模块，JSON NDJSON 文件日志 + 控制台输出，按日轮转，保留 30 天历史。
  - ✅ 第 6 步：记录运行错误与状态 — `ErrorTracker` (app/qa/error_tracker.py) + `RunLogStore` (app/storage/database.py) + test_error_tracker.py (15) + test_pipeline_integration.py (16)。
  - ✅ 第 7 步：明确 dev 文档更新约定 — 已写入 CLAUDE.md，每完成一步立刻更新对应任务清单，不允许在未更新文档的情况下切换子智能体。

- **当前专项测试状态**
  - `tests/test_error_tracker.py`：**15/15** 通过；
  - `tests/test_pipeline_integration.py`：**16/16** 通过；
  - 全量回归测试：`pytest tests -q`，**1644/1644** 个测试通过。

- **循环导入修复**
  - 修复了 `app/analysis/engine.py` 中未使用的 `from app.storage import PromptProfileStore, RunLogStore` 导入，解决了 `app.storage → app.analysis → app.analysis.engine → app.storage` 的循环导入问题。

- **关键文件**
  - qa 模块：`app/qa/__init__.py`、`app/qa/error_tracker.py` — ErrorTracker / ErrorSummary
  - 日志模块：`app/logger/__init__.py`、`app/logger/setup.py`、`app/logger/formatter.py`
  - 存储层：`app/storage/database.py` — RunLogStore / PromptProfileStore / ChainScoreStore / InfoChainStore
  - 集成测试：`tests/test_pipeline_integration.py` — 端到端流水线测试
  - 调度测试：`tests/test_scheduler.py` — 调度与重试测试

- **项目全阶段完成状态**
  - 10/10 子任务全部完成：project-bootstrap, source-collection, normalization-pipeline, entity-theme-tagging, information-chain, llm-analysis, a-share-mapping, reporting-output, scheduler-automation, qa-observability

