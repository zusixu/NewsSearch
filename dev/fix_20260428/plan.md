# Plan — 技术债修复 2026-04-28

## 执行计划

### P0 批次（紧急修复，T1/T2 并行）

#### T1: web_access_transport.py 日志补全

**目标**：为 805 行网络 I/O 代码添加完整日志覆盖。

**步骤**：
1. 在文件顶部添加 `from app.logger import get_logger; logger = get_logger(__name__)`
2. CDPProxyClient 每个方法添加日志：
   - `is_available()`: debug 记录检查结果
   - `new_tab()`: info 记录 URL，error 记录失败
   - `eval_js()`: debug 记录执行，error 记录失败
   - `navigate()`: info 记录 URL，error 记录失败
   - `close_tab()`: debug 记录关闭，warning 记录失败
   - `get_page_text()`: info 记录 URL + 耗时，warning 记录降级
   - `search_bing()`: info 记录查询 + 结果数
3. WebAccessTransport 每个方法添加日志：
   - `execute()`: info 记录开始/完成，warning 记录部分失败
   - `_build_queries()`: debug 记录生成查询列表
   - `_search()`: info 记录查询 + 后端选择 + 结果数 + 耗时
   - `_fetch_url()`: info 记录 URL + 状态，warning 记录失败
4. 所有 `except Exception: pass` / `return None` → 添加 `logger.exception()` 或 `logger.warning()`
5. `time.sleep(2)` / `time.sleep(3)` 前添加 `logger.debug("Waiting for page load...")`
6. 运行 `pytest tests/ -q` 回归

**验收标准**：
- 0 处 `except Exception: pass`（无日志版）
- 所有网络 I/O 方法有 info 级别日志
- 所有异常路径有 warning/error 级别日志
- 全量测试通过

---

#### T2: ReAct finalize 异常处理

**目标**：消除 `except Exception: pass`，添加日志和降级标记。

**步骤**：
1. 在 `app/analysis/react/engine.py:499` 的 `except Exception: pass` 改为：
   ```python
   except Exception:
       logger.exception("ReAct finalize failed, falling back to heuristic synthesis")
   ```
2. 在降级返回的 `AnalysisResponse` metadata 中添加 `finalize_fallback: True` 标记（如数据结构支持）
3. 运行 `pytest tests/test_react_engine.py -v`
4. 运行 `pytest tests/ -q` 回归

**验收标准**：
- 无 `except Exception: pass`
- 降级时日志记录完整
- 降级行为不变
- 全量测试通过

---

### P1 批次（架构修复，T3→T4 顺序，T5 并行）

#### T3: 存储层分层修复 + ChatMessage/PromptRenderer 迁移

**步骤 1 — 迁移 ChatMessage/PromptRenderer**：
1. 将 `github_models.py:64-77` 的 `ChatMessage` 移到 `contracts.py`
2. 将 `github_models.py:136-157` 的 `PromptRenderer` 移到 `contracts.py`
3. 在 `github_models.py` 中添加 `from app.analysis.adapters.contracts import ChatMessage, PromptRenderer` 并 re-export
4. 更新 `openai_compatible.py:41` 的导入路径
5. 更新 `engine.py:31` 的导入路径
6. 更新 `react/engine.py:44` 的导入路径
7. 运行 `pytest tests/test_analysis_adapter_contracts.py tests/test_github_models_adapter.py tests/test_analysis_engine.py tests/test_react_engine.py -v`
8. 运行 `pytest tests/ -q` 回归

**步骤 2 — 解除 storage→analysis 依赖**：
1. 在 `app/storage/` 下新建 `types.py`
2. 将 `PromptTaskType` 从 `app/analysis/adapters/contracts.py` 移到 `app/storage/types.py`
3. 将 `PromptProfileConfig` 和 `TaskTemplateMapping` 从 `app/analysis/prompts/profile.py` 移到 `app/storage/types.py`
4. `contracts.py` 和 `profile.py` 改为从 `app.storage.types` 导入并 re-export
5. `database.py:30-32` 的导入改为从 `app.storage.types` 导入
6. 运行 `pytest tests/test_storage.py tests/test_analysis_adapter_contracts.py tests/test_prompt_profile.py -v`
7. 运行 `pytest tests/ -q` 回归

**验收标准**：
- `database.py` 不再导入 `app/analysis/` 下任何模块
- `ChatMessage` 和 `PromptRenderer` 定义在 `contracts.py`
- 所有 re-export 保持向后兼容
- 全量测试通过

---

#### T4: ReAct 引擎 duck-typing 修复

**目标**：在 `AnalysisAdapter` Protocol 中添加 `analyse_raw()` 方法，消除私有方法依赖。

**步骤**：
1. 在 `contracts.py` 的 `AnalysisAdapter` Protocol 中添加：
   ```python
   def analyse_raw(self, analysis_input: AnalysisInput) -> dict[str, Any]: ...
   ```
2. 在 `github_models.py` 的 `GitHubModelsAdapter` 中实现 `analyse_raw()`
3. 在 `openai_compatible.py` 的 `OpenAICompatibleAdapter` 中实现 `analyse_raw()`
4. 在 `engine.py` 的 `DryRunAnalysisAdapter` 中实现 `analyse_raw()`
5. 重构 `react/engine.py` 的 `_call_llm_raw` 为调用 `self.adapter.analyse_raw()`
6. 运行 `pytest tests/test_react_engine.py tests/test_analysis_engine.py -v`
7. 运行 `pytest tests/ -q` 回归

**验收标准**：
- `_call_llm_raw` 不再访问适配器私有方法（`_render_messages`, `_build_payload`, `_post`）
- 新适配器只需实现 Protocol 方法
- 全量测试通过

---

#### T5: apply_override 补全

**步骤**：
1. 确认 `AppConfig` schema 中 `search_keywords`、`web_sources`、`prompt_overrides`、`akshare_providers` 对应字段
2. 如字段不存在，在 `schema.py` 中添加
3. 在 `apply_override()` 函数末尾添加回写逻辑
4. 添加测试覆盖回写行为
5. 运行 `pytest tests/test_override.py -v`
6. 运行 `pytest tests/ -q` 回归

**验收标准**：
- `apply_override` 解析的所有字段都回写到 `AppConfig`
- 新增测试覆盖
- 全量测试通过

---

### P2 批次（功能修复，T6/T7 并行）

#### T6: 关系类型覆盖级联修复

**目标**：三阶段流水线保留最强语义关系，不盲目覆盖。

**步骤**：
1. 修改 `temporal_connection.py:_reorder_chain`：重排后仅在节点顺序确实改变时设 `TEMPORAL`，未改变则保留原 `relation_to_prev`
2. 修改 `upstream_downstream.py:_reorder_chain`：仅在确认上下游映射时设 `UPSTREAM_DOWNSTREAM`，未映射则保留原值
3. 更新 `tests/test_temporal_connection.py`：验证 SAME_TOPIC 保留场景
4. 更新 `tests/test_upstream_downstream.py`：验证 TEMPORAL 保留场景
5. 运行 `pytest tests/test_candidate_generation.py tests/test_temporal_connection.py tests/test_upstream_downstream.py -v`
6. 运行 `pytest tests/ -q` 回归

**语义强度**：`UPSTREAM_DOWNSTREAM` > `TEMPORAL` > `SAME_TOPIC`

**验收标准**：
- 同主题链保留 `SAME_TOPIC`（除非后续阶段判定更强关系）
- 时序链保留 `TEMPORAL`（除非上下游阶段判定更强关系）
- 上下游链正确设置 `UPSTREAM_DOWNSTREAM`
- 全量测试通过

---

#### T7: 死代码清理 + 时效性评分 + ranking 决策

**子任务 7a — 时效性评分 (#5)**：
1. 修改 `_calculate_timeliness_score` 基于时间差计算：
   - 当天新闻 → 100
   - 1 天内 → 90
   - 3 天内 → 80
   - 7 天内 → 60
   - 更早 → 40
2. 从 mapping evidence 中获取 `published_at` 时间戳
3. 添加测试

**子任务 7b — 死代码删除 (#6 + 常见陷阱)**：
1. 删除 `engine.py:337-338` use_profile 死代码
2. 删除 `news_item.py:51-52` 空 TYPE_CHECKING 块
3. 删除 `date_filter.py:28` 未使用 `import copy`
4. 清理 `entity_types.py:25` 未使用导入

**子任务 7c — ranking 模块决策 (#10)**：
1. 删除 `app/ranking/__init__.py`（空文件）
2. 删除 `app/ranking/` 目录
3. 确认无外部导入引用该模块
4. 在 `PROJECT_INDEX.md` 中移除 ranking 模块条目

**子任务 7d — 适配器解析去重 (#11)**：
1. 在 `contracts.py` 中提取 `_parse_analysis_json(raw_json: str) -> dict` 共享函数
2. 两个适配器的 `_parse_response` 调用共享函数 + 各自特有逻辑
3. 运行适配器测试

**验收标准**：
- 无死代码、无未使用导入
- 时效性评分基于时间差动态计算
- ranking 空模块已删除
- 适配器解析共享核心逻辑
- 全量测试通过

---

### P3 批次（功能实装）

#### T8: ReAct 工具实装

**子任务 8a — web_search 实装**：
1. 通过依赖注入将 `WebAccessTransport` 实例传入 ReAct engine
2. `web_search` 工具调用 `transport._search()` 执行多后端搜索
3. 返回结构化搜索结果（标题 + URL + 摘要）
4. 懒加载 transport 依赖

**子任务 8b — akshare_query 实装**：
1. 通过依赖注入将 AkShare 查询能力传入 ReAct engine
2. `akshare_query` 工具调用 `ak.stock_zh_a_hist()` 等接口获取行情
3. 懒加载 akshare：函数内 `import akshare`
4. 返回结构化行情数据

**验收标准**：
- `web_search` 返回真实搜索结果
- `akshare_query` 返回真实行情数据
- 第三方依赖懒加载
- 全量测试通过

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| T3 迁移导致循环导入 | 编译失败 | 分步迁移，每步回归测试 |
| T6 关系类型保留逻辑复杂 | 引入新 bug | 充分测试边界场景 |
| T8 AkShare API 不稳定 | 工具调用失败 | 保留降级逻辑，错误时返回提示信息 |
| 全量回归耗时 | 开发效率 | 每个子任务只跑相关测试，完成批次后全量回归 |
