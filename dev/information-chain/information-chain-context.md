# information-chain

## 关键文件

- `app/chains/__init__.py` — 包入口，导出 `ChainNode`、`InformationChain`、`RelationType`、`build_chain`、`group_same_topic`、`apply_temporal_order`、`apply_upstream_downstream_order`、`generate_candidate_chains`、`ChainEvidenceBundle`、`collect_chain_evidence`、`collect_all_evidence`
- `app/chains/chain.py` — 信息链核心数据结构；`ChainNode.relation_to_prev` 现为 `RelationType | None`
- `app/chains/relation_type.py` — 关系类型枚举（节点 2 新增）
- `app/chains/same_topic_grouping.py` — 同主题聚合（节点 3 新增）；`group_same_topic` 公开 API
- `app/chains/temporal_connection.py` — 时序连接（节点 4 新增）；`apply_temporal_order` 公开 API
- `app/chains/upstream_downstream.py` — 上下游连接（节点 5 新增）；`apply_upstream_downstream_order` 公开 API
- `app/chains/candidate_generation.py` — 候选信息链生成（节点 6 新增）；`generate_candidate_chains` 公开 API
- `app/chains/evidence_retention.py` — 证据集合保留（节点 7 新增）；`ChainEvidenceBundle`、`collect_chain_evidence`、`collect_all_evidence` 公开 API
- `app/entity/tagged_output.py` — 上游输入（`TaggedOutput`），已完成
- `app/entity/` — 实体/主题标签体系，已完成
- `tests/test_chain.py` — 信息链结构完整性测试（39 个测试用例）
- `tests/test_relation_type.py` — 关系类型测试（节点 2 新增，40 个测试用例）
- `tests/test_same_topic_grouping.py` — 同主题聚合专项测试（节点 3 新增，36 个测试用例）
- `tests/test_temporal_connection.py` — 时序连接专项测试（节点 4 新增，36 个测试用例）
- `tests/test_upstream_downstream.py` — 上下游连接专项测试（节点 5 新增，48 个测试用例）
- `tests/test_candidate_generation.py` — 候选信息链生成专项测试（节点 6 新增，35 个测试用例）
- `tests/test_evidence_retention.py` — 证据集合保留专项测试（节点 7 新增，41 个测试用例）

## 决策记录

- 关系类型至少包括因果、时间延续、上下游影响、同主题发酵。
- 链路必须保留证据，而不是只保留结论。
- **`ChainNode`**：封装 `TaggedOutput` 引用（不拷贝）+ `position`（0-based 序号）+
  `relation_to_prev: RelationType | None = None`（None 表示链首节点或关系未知）。
- **`InformationChain`**：frozen dataclass，持有有序 `ChainNode` 元组、聚合
  `theme_ids` 与 `entity_type_ids`（跨节点并集，去重升序）。
- **`build_chain`**：接受 `chain_id` + `Sequence[TaggedOutput]`，自动赋 position，
  聚合标签 ID，返回不可变 `InformationChain`。
- `__post_init__` 强制校验：chain_id 非空、nodes 非空、position 连续递增。
- **`RelationType`**：`str, Enum` 子类，4 个成员值为中文标签（因果 / 时间延续 /
  上下游影响 / 同主题发酵），直接可 JSON 序列化，支持 `RelationType(value)` 反向构造。
- **`group_same_topic`**（节点 3）：
  - 使用路径压缩 Union-Find 实现传递闭包分组（A-B 共享、B-C 共享 ⇒ A、B、C 同组）。
  - `theme_ids` 为空的输入各自形成 singleton 链，**不丢弃**，保留数据供后续阶段处理。
  - 组内节点保留原始输入顺序（不按时间重排；排序由后续时序节点负责）。
  - 组间按组内首个节点的原始索引升序排列（确定性）。
  - 链 ID 格式：`same-topic-NNNN`（4 位零填充，1-based）。
  - 首节点 `relation_to_prev = None`，后续节点 `relation_to_prev = RelationType.SAME_TOPIC`。
  - 不负责评分、候选筛选、时序排序或上下游连接。
- **`apply_temporal_order`**（节点 4，自主决策）：
  - **自主决策**：用户不在线期间确定：在现有 `InformationChain` 节点内直接重排，而非引入多关系存储。
    同主题语义由链的分组来源和链级别 `theme_ids` 保留，本模块不发明多关系存储。
  - 排序键：`node.tagged_output.event.occurred_at`（`"YYYY-MM-DD"` 字符串），字典序等价于时间序。
  - 空字符串（日期未知）视为最大值，排在所有已知日期之后。
  - 相同日期（含均为空）的节点保持原始相对顺序（Python 内置稳定排序）。
  - 非破坏性：输入链不被修改，返回全新对象。
  - 首节点 `relation_to_prev = None`，其余节点 `relation_to_prev = RelationType.TEMPORAL`。
  - `chain_id`、`theme_ids`、`entity_type_ids`、`tagged_output` 引用原样保留；`position` 重赋 0-based。
  - 不负责上下游连接、评分、候选筛选或证据过滤。
- **`generate_candidate_chains`**（节点 6）：
  - 流水线组合：`group_same_topic` → `apply_temporal_order` → `apply_upstream_downstream_order`。
  - 接受 `Sequence[TaggedOutput]`，返回 `list[InformationChain]`。
  - 空输入返回空列表；singleton/无主题节点不丢弃（保守保留，行为继承自上游阶段）。
  - 链 ID 由 `group_same_topic` 生成（`same-topic-NNNN`），后续阶段原样保留。
  - `tagged_output` 引用不变，证据通过 `node.tagged_output.evidence_links` 可达。
  - 确定性：相同输入始终产生相同链数量和顺序。
  - **不负责排名、评分、重要性过滤、Top-K 选择或 LLM 分析**。
  - **自主决策**：用户不在线期间确定：数据模型无归一化供应链阶段字段，从 `TaggedOutput.theme_ids` 推断粗粒度阶段（高精度低召回）。
  - 阶段映射（确定性）：upstream = {semiconductor, memory, gpu, optical_module, storage}；midstream = {compute, supply_chain}；downstream = {cloud, foundation_model, ai_application, ai}；无命中 = unknown。
  - 多阶段优先级：命中多个桶时取最上游阶段（upstream > midstream > downstream）。
  - unknown 阶段节点排在所有已知阶段之后，保持原始相对顺序，不丢弃。
  - 非破坏性：输入链不被修改，返回全新对象。
  - 首节点 `relation_to_prev = None`，其余节点 `relation_to_prev = RelationType.UPSTREAM_DOWNSTREAM`。
  - `chain_id`、`theme_ids`、`entity_type_ids`、`tagged_output` 引用原样保留；`position` 重赋 0-based。
  - 不负责候选选择、评分或跨链合并。
  - 局限性：依赖 theme_ids 字面量 ID，拼写变体或新增主题无法自动覆盖；详见模块 docstring。
- **`collect_chain_evidence` / `collect_all_evidence` / `ChainEvidenceBundle`**（节点 7）：
  - `ChainEvidenceBundle`：`frozen=True` dataclass，字段为 `chain_id: str`、`source_items: tuple[NewsItem, ...]`、`evidence_links: tuple[EvidenceLink, ...]`。
  - `collect_chain_evidence`：遍历 `chain.nodes`（按 `position` 升序），从 `node.tagged_output.event.source_items` 和 `node.tagged_output.evidence_links` 聚合；`source_items` 以对象身份（`id(...)`）去重，`evidence_links` 以值相等（`==`/`hash`）去重；首见顺序保留。
  - `collect_all_evidence`：对 `Sequence[InformationChain]` 每条链独立调用 `collect_chain_evidence`，返回顺序与输入一致；链间不做跨链去重。
  - 不拷贝对象：所有引用原样保留，不做深拷贝，`is` 恒等追溯有效。
  - 不修改输入、不访问 DB、不排序证据、不过滤证据。

## 待补充

- 链路评分规则。
- 多事件合并阈值。

## 当前进度

- ✅ 节点 1「定义信息链数据结构」已完成：
  - 新增 `app/chains/chain.py`（`ChainNode`、`InformationChain`、`build_chain`）
  - 更新 `app/chains/__init__.py` 导出公开 API
  - 新增 `tests/test_chain.py`（39 个测试全部通过）
  - 独立验收已完成：`app.chains` 公开导入正常，且不影响既有 entity + normalization 聚焦回归（635/635 通过）

- ✅ 节点 2「定义关系类型」已完成：
  - 新增 `app/chains/relation_type.py`（`RelationType` str+Enum，4 个成员）
  - 更新 `app/chains/chain.py`：`ChainNode.relation_to_prev` 类型从 `str | None` → `RelationType | None`
  - 更新 `app/chains/__init__.py`：新增 `RelationType` 导出
  - 新增 `tests/test_relation_type.py`（40 个测试全部通过）
  - 独立验收已完成：信息链结构 + 关系类型专项测试 **79/79** 通过，且既有 entity + normalization 聚焦回归 **635/635** 通过

- ✅ 节点 3「实现同主题聚合」已完成：
  - 新增 `app/chains/same_topic_grouping.py`（`group_same_topic`，Union-Find 传递闭包）
  - 更新 `app/chains/__init__.py`：新增 `group_same_topic` 导出
  - 新增 `tests/test_same_topic_grouping.py`（36 个测试全部通过）
  - 独立验收已完成：信息链聚焦测试 **115/115** 通过（same-topic 36 + chain 39 + relation 40），既有 entity + normalization 聚焦回归 **635/635** 通过

- ✅ 节点 4「实现时序连接」已完成：
  - 新增 `app/chains/temporal_connection.py`（`apply_temporal_order`，稳定排序 + 哨兵置后）
  - 更新 `app/chains/__init__.py`：新增 `apply_temporal_order` 导出
  - 新增 `tests/test_temporal_connection.py`（36 个测试全部通过）
  - 自主决策记录：重排现有节点而非多关系存储，同主题语义由链级别 `theme_ids` 保留，
    详见模块 docstring 和本文件「决策记录」。
  - 独立验收已完成：信息链聚焦测试 **151/151** 通过（temporal 36 + same-topic 36 + chain 39 + relation 40）

- ✅ 节点 5「实现上下游连接」已完成：
  - 新增 `app/chains/upstream_downstream.py`（`apply_upstream_downstream_order`，theme_ids 启发式阶段推断 + 稳定排序）
  - 更新 `app/chains/__init__.py`：新增 `apply_upstream_downstream_order` 导出
  - 新增 `tests/test_upstream_downstream.py`（48 个测试全部通过）
  - 自主决策记录：从 `TaggedOutput.theme_ids` 推断供应链阶段（高精度低召回），多阶段取最上游，unknown 置后，
    详见模块 docstring 和本文件「决策记录」。
  - 独立验收已完成：信息链聚焦测试 **199/199** 通过（upstream-downstream 48 + temporal 36 + same-topic 36 + chain 39 + relation 40）

- ✅ 节点 6「生成候选信息链」已完成：
  - 新增 `app/chains/candidate_generation.py`（`generate_candidate_chains`，三阶段流水线组合）
  - 更新 `app/chains/__init__.py`：新增 `generate_candidate_chains` 导出
  - 新增 `tests/test_candidate_generation.py`（35 个测试全部通过）
  - 流水线顺序：`group_same_topic` → `apply_temporal_order` → `apply_upstream_downstream_order`
  - 独立验收已完成：信息链聚焦测试 **234/234** 通过（candidate 35 + upstream-downstream 48 + temporal 36 + same-topic 36 + chain 39 + relation 40）

- ✅ 节点 7「保留证据集合」已完成：
  - 新增 `app/chains/evidence_retention.py`（`ChainEvidenceBundle`、`collect_chain_evidence`、`collect_all_evidence`）
  - 更新 `app/chains/__init__.py`：新增 `ChainEvidenceBundle`、`collect_chain_evidence`、`collect_all_evidence` 导出
  - 新增 `tests/test_evidence_retention.py`（41 个测试全部通过）
  - 聚合规则：`source_items` 以对象身份（`id(...)`）去重，`evidence_links` 以值相等（`==`）去重，均保留首见顺序
  - 独立验收已完成：信息链聚焦测试 **275/275** 通过（evidence_retention 41 + candidate 35 + upstream-downstream 48 + temporal 36 + same-topic 36 + chain 39 + relation 40）

## 下一步

- 所有 7 个节点已全部完成。链路评分规则和多事件合并阈值（见「待补充」）可作为后续扩展。

## 交接要求

- 上下文快用完时，先回写当前进度、修改文件、阻塞项和下一步，再切换新的子智能体。
