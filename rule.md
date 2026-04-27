# rule.md — MM 项目开发规范

> 本文档定义项目后续优化与开发工作的编码规范、架构约束和操作纪律。
> 任何 AI 智能体在修改本项目代码前，必须先阅读 `CLAUDE.md`、`PROJECT_INDEX.md` 和本文件。

---

## 1. 核心原则

1. **最小变更**：只改需要改的，不顺手重构、不添加"顺手优化"
2. **数据不可变**：所有 dataclass 默认 `frozen=True`；如需可变，必须注释说明原因
3. **分层单向依赖**：上层可依赖下层，下层不得依赖上层（违反之处需标注并逐步修复）
4. **防御式 I/O，信任式内部**：只在系统边界（网络请求、文件读取、用户输入）做校验，内部函数间信任类型
5. **改动可追溯**：每次修改必须关联到具体问题或需求，禁止无目的的代码调整

---

## 2. 代码风格

### 2.1 Python 规范

- Python 3.11+，使用 `type hints`（`list[X]` 而非 `List[X]`，`str | None` 而非 `Optional[str]`）
- 行宽 120 字符
- 使用 `dataclass(frozen=True)` 作为数据模型首选
- 使用 `str, Enum` 枚举以确保 JSON 序列化兼容
- 使用 `Protocol` + `@runtime_checkable` 定义接口
- 异常层次：自定义异常继承 `ValueError` 或 `Exception`，携带上下文字段

### 2.2 命名

| 类型 | 风格 | 示例 |
|---|---|---|
| 模块/包 | `snake_case` | `url_dedup.py`, `evidence_retention.py` |
| 类 | `PascalCase` | `NewsItem`, `AnalysisEngine` |
| 函数/方法 | `snake_case` | `build_chain()`, `grade_credibility()` |
| 常量 | `UPPER_SNAKE_CASE` | `_RANK_UPSTREAM`, `_UNKNOWN_DATE_SENTINEL` |
| 私有符号 | `_` 前缀 | `_build_render_context()`, `_sanitize_key()` |
| dataclass 字段 | `snake_case` | `source_credibility`, `chain_id` |

### 2.3 注释

- **不写** WHAT 注释（代码本身已说明）
- **只在** WHY 不显然时写注释：隐含约束、反直觉决策、历史原因、已知限制
- 中文注释适用于领域相关的决策记录（如产业链定义理由）
- 每个模块顶部的 docstring 应说明职责和管道阶段位置

### 2.4 导入

- 标准库 → 第三方 → 项目内部，各组之间空一行
- 第三方依赖（akshare, requests, bs4 等）使用**懒加载**（函数内 import），避免模块级 ImportError
- 避免 `from module import *`
- 包 `__init__.py` 的 re-export 使用 `# noqa: F401`

---

## 3. 架构约束

### 3.1 分层依赖规则

```
main.py → analysis → chains → entity → normalize → models
                  → mapping → entity
                  → storage ← analysis（⚠️ 已违反，需修复）
         → collectors → models
         → reports → mapping → models
         → scheduler → main（subprocess 调用）
         → qa → storage
```

**绝对禁止的依赖方向**：
- `models/` 不得依赖任何其他 `app/` 子包
- `normalize/` 不得依赖 `entity/`、`chains/`、`analysis/`、`mapping/`
- `storage/` 不得依赖 `analysis/`（当前已违反，见已知问题 #8）

**已知违规需逐步修复**：
- `app/storage/database.py` 导入 `app/analysis/adapters/contracts` 和 `app/analysis/prompts/profile`

### 3.2 数据流管道契约

每个管道阶段遵循统一签名模式：

```python
def pipeline_stage(items: list[InputType]) -> list[OutputType]:
```

- **不修改输入**：始终返回新对象
- **保持顺序**：输出顺序应与输入语义一致
- **保持数量**：过滤阶段可以减少数量，但不改变阶段不应增减

### 3.3 适配器模式

- 所有 LLM 适配器必须实现 `AnalysisAdapter` Protocol
- 适配器之间共享的类型（`ChatMessage`, `PromptRenderer`）应定义在 `contracts.py` 或独立 `types.py`，不应定义在具体适配器中
- 适配器通过构造函数注入依赖（renderer, env, http client），便于测试

### 3.4 采集器模式

- 所有采集器继承 `BaseCollector` ABC
- 采集结果通过 `CollectResult` 返回，错误通过 `errors` 列表累积（不中断）
- 第三方库懒加载：`_import_xxx()` 函数模式
- 缓存通过 `CollectionCache` 统一管理

---

## 4. 数据模型规范

### 4.1 Frozen Dataclass 规则

- 所有数据模型默认 `frozen=True`
- 需要可变的场景（如 `ReActSession` 累积步骤）必须注释说明原因
- `default_factory=dict` 与 `frozen=True` 不兼容 — 改用 `field(default_factory=dict)` 时需审查

### 4.2 跨层 ID 传递

- `RawDocument` → `NewsItem.raw_refs` 列表追溯
- `NewsItem` → `EventDraft.source_items` 列表追溯
- 链 ID 使用确定性格式（如 `same-topic-0001`），不使用随机 UUID（除非无自然键）

### 4.3 Metadata 字典

- `metadata` 字段使用 `dict[str, Any]`
- 各管道阶段写入自己命名空间的键（如 `time_normalization`, `source_credibility`）
- 浅拷贝风险：`copy.copy(metadata)` 不保护嵌套 dict/list

---

## 5. 测试规范

### 5.1 基本要求

- 每个新模块必须有对应测试文件
- 测试文件命名：`tests/test_<module_name>.py`
- 使用 pytest；`parametrize` 覆盖边界情况
- 每次修改后运行 `pytest tests/ -q` 确认不引入回归

### 5.2 测试隔离

- 采集器测试使用 `sleeper=lambda _: None` 跳过真实等待
- LLM 测试使用 `DryRunAnalysisAdapter`，不调用真实 API
- 数据库测试使用 `:memory:` SQLite
- 网络测试使用 mock 或 `NullTransport`

### 5.3 覆盖重点

- 数据模型的 `__post_init__` 验证逻辑
- 管道阶段的边界输入（空列表、None 字段、非法值）
- 去重/过滤的保留-丢弃决策
- 错误路径（网络失败、认证失败、超时）

---

## 6. 日志规范

### 6.1 强制日志的场景

- **所有网络 I/O**：请求开始、响应状态码、耗时
- **重试/降级**：每次重试原因、降级决策
- **数据丢弃**：过滤/去重移除的项目及原因
- **截断**：列表截断时记录原始数量与保留数量

### 6.2 禁止的模式

- `except Exception: pass` — 至少 `logger.exception()` 或 `logger.warning()`
- `except Exception: return None` — 记录异常后再返回
- 无任何日志的网络请求（⚠️ `web_access_transport.py` 当前违反此规则）

### 6.3 日志格式

- 使用 `app/logger/` 提供的 NDJSON 格式
- 通过 `logging.getLogger(__name__)` 获取 logger
- `extra={}` 传递结构化字段

---

## 7. 配置规范

### 7.1 配置层级

1. `.env` 文件（密钥/令牌）— 不提交
2. `config.yaml`（业务配置）— 可提交
3. `config/override.example.yaml`（运行时覆盖模板）
4. CLI 参数（最高优先级）

### 7.2 新增配置项

- 在 `app/config/schema.py` 的对应 `*Config` dataclass 中添加字段
- 提供合理默认值
- 在 `AppConfig.validate()` 中添加校验
- 更新 `config.yaml` 注释

### 7.3 环境变量

- 密钥类通过 `.env` 文件管理，不硬编码
- `.env` 中 key 优先级高于 `os.environ`（项目设计决策）

---

## 8. 数据库规范

### 8.1 Schema 变更

- 所有 DDL 使用 `IF NOT EXISTS`（幂等）
- 只做加法：新增表/列，不做破坏性修改
- 如需数据迁移，编写独立迁移脚本
- 修改后更新 `tests/test_storage.py`

### 8.2 Store 类

- 每个 Store 接受 `sqlite3.Connection` 构造注入
- 提供完整的 CRUD（不只是 insert）
- 不使用 ORM — 使用 stdlib `sqlite3`

---

## 9. 操作纪律

### 9.1 修改前

1. 阅读 `PROJECT_INDEX.md` 了解模块定位和依赖
2. 阅读 `rule.md` 确认规范约束
3. 阅读 `dev/<task>/` 中相关 context.md 了解历史决策
4. 运行 `pytest tests/ -q` 确认基线通过

### 9.2 修改中

1. 每完成一个逻辑步骤，立即运行相关测试
2. 新增代码必须符合本规范
3. 不引入新的分层违规
4. 不添加未使用的导入或变量

### 9.3 修改后

1. 运行 `pytest tests/ -q` 全量回归
2. 更新 `PROJECT_INDEX.md` 中的受影响条目
3. 如新增模块或类，更新模块速查表
4. 如修复已知问题，从已知问题清单中移除

---

## 10. 常见陷阱

| 陷阱 | 说明 | 参考 |
|---|---|---|
| `mapping/report.py` vs `reports/core.py` | 不要修改 `mapping/report.py`，它是旧版重复；权威实现在 `reports/core.py` | 已知问题 #1 |
| `ranking/` 空模块 | 排序逻辑在 `analysis/engine.py`，不在 `ranking/` | 已知问题 #10 |
| 关系类型覆盖 | `candidate_generation` 逐级覆盖 `relation_to_prev`，修改单阶段关系不会传递到最终结果 | 已知问题 #2 |
| ReAct duck-typing | `_call_llm_raw` 访问适配器私有方法，新增适配器必须暴露 `_render_messages`, `_build_payload`, `_post` | 已知问题 #3 |
| `source_credibility` 用 `dataclasses.replace` | 其他 normalize 模块用 `NewsItem(...)` 构造，二者不一致 | 代码审查 |
| `news_item.py` 空 `TYPE_CHECKING` 块 | 死代码，应清理 | 代码审查 |
| `date_filter.py` 未使用的 `import copy` | 死导入，应清理 | 代码审查 |
| `entity_types.py` 未使用的 `Optional` | 死导入，应清理 | 代码审查 |
| `apply_override` 不完整 | `search_keywords`/`web_sources`/`prompt_overrides` 已解析但不回写 | 已知问题 #9 |
| Prompt 模板双花括号 | JSON 模板中的 `{{` / `}}` 是 Python `str.format()` 转义，编辑模板时务必保留 | 架构约束 |
| 搜索关键词后缀 | `web_access_transport._build_queries` 自动追加 `" AI investment news"` 后缀 | 代码审查 |
| Caixin 回填限制 | `_fetch_caixin` 无日期过滤参数，回填时返回当前头条 | 已知限制 |

---

## 11. 优先修复路线

建议按以下顺序处理技术债：

1. **`mapping/report.py` 去重** — 删除旧版或改为 thin re-export，更新 `mapping/__init__.py`
2. **`web_access_transport.py` 日志** — 为所有网络 I/O 和异常路径添加 logging
3. **ReAct finalize 异常处理** — 将 `except Exception: pass` 改为 `logger.exception()` + 降级策略
4. **存储层分层修复** — 将 `PromptProfileConfig`/`PromptTaskType` 移到 storage 或独立 types 模块
5. **`apply_override` 补全** — 将解析的覆盖字段回写到 `AppConfig`
6. **`ChatMessage`/`PromptRenderer` 迁移** — 从 `github_models.py` 移到 `contracts.py` 或 `types.py`
7. **关系类型保留** — 考虑在 `ChainNode` 上支持多关系（或记录历史关系到 metadata）
8. **ReAct 工具实装** — 补全 `web_search` 和 `akshare_query` 的真实实现
9. **时效性评分** — 替换硬编码 80.0 为基于发布时间差的计算
10. **`ranking/` 模块** — 决定是实装还是删除空包
