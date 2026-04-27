# pipeline-refactoring — 流水线架构重构

## 目标

基于 plan.md 中的"流水线架构重构计划"，实现三项核心改动：
1. 采集层简化（CopilotResearchCollector 改为可选）
2. URL 溯源透传与报告展示
3. ReAct 多步分析引擎（核心重构）

---

## 阶段与文件清单

### Phase 1: 采集层简化
| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `config.yaml` | 修改 | `copilot_research: false`（默认关闭） |
| `app/collectors/copilot_research_collector.py` | 修改 | `is_enabled()` 尊重配置，不再强制返回 `True` |
| `app/main.py` | 修改 | `_create_collectors()` 按配置决定是否实例化 |

### Phase 2: URL 溯源透传
| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `app/chains/evidence_retention.py` | 修改 | `ChainEvidenceBundle` 新增 `source_urls: tuple[str, ...]` |
| `app/mapping/schema.py` | 修改 | `DailyReportChainEntry` 新增 `source_urls` |
| `app/reports/core.py` | 修改 | Markdown/JSON 渲染增加"来源链接"区域 |

### Phase 3: ReAct 多步分析引擎（核心重构）
| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `app/analysis/react/__init__.py` | 新建 | 公共 API 导出 |
| `app/analysis/react/tools.py` | 新建 | Tool/ToolRegistry 协议；web_search/web_fetch/akshare_query |
| `app/analysis/react/session.py` | 新建 | ReActStep/ReActSession 状态机 |
| `app/analysis/react/prompts.py` | 新建 | GROUPER_PROMPT/REACT_SYSTEM_PROMPT/REACT_FINALIZE_PROMPT |
| `app/analysis/react/engine.py` | 新建 | ReActAnalysisEngine：分组→ReAct→排序 |
| `app/analysis/prompts/templates/grouper.json` | 新建 | 分组策略模板 |
| `app/analysis/prompts/templates/react_step.json` | 新建 | ReAct 单步模板 |
| `app/analysis/prompts/templates/react_finalize.json` | 新建 | ReAct finalize 模板 |
| `app/analysis/adapters/contracts.py` | 修改 | 新增 PromptTaskType: GROUPER/REACT_STEP/REACT_FINALIZE |
| `app/analysis/engine.py` | 修改 | 整合 ReActAnalysisEngine；支持 mode 切换 |
| `app/analysis/__init__.py` | 修改 | 导出 react 模块公共 API |

### Phase 4: 配置与模式开关
| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `config.yaml` | 修改 | 新增 `analysis:` 配置节 |
| `app/config/schema.py` | 修改 | 新增 `AnalysisConfig` dataclass |
| `app/config/loader.py` | 修改 | 新增 `_build_analysis()` builder |
| `app/main.py` | 修改 | CLI 新增 `--analysis-mode {react,legacy}` |

### Phase 5: 测试
| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `tests/test_react_tools.py` | 新建 | ToolRegistry 注册/执行、各工具 fallback |
| `tests/test_react_session.py` | 新建 | ReActStep/ReActSession 状态机 |
| `tests/test_react_engine.py` | 新建 | 分组逻辑、多步迭代、finalize、跨组排序 |
| `tests/test_url_preservation.py` | 新建 | URL 全链路透传测试 |
| `tests/test_collector_optional.py` | 新建 | CopilotResearchCollector 可选启用/禁用 |

---

## 依赖关系

```
Phase 1 (采集层) ─────────┐
                          ├──→ Phase 4 (配置) ──→ Phase 5 (测试)
Phase 2 (URL溯源) ────┘   │
                          │
Phase 3 (ReAct引擎) ──────┘
```

- Phase 1, 2, 3 互不依赖，可完全并行开发
- Phase 4 依赖 Phase 3（需要 ReAct 配置字段），也略依赖 Phase 1
- Phase 5 依赖所有前序阶段

---

## 关键决策记录

### Phase 3 决策
- ReAct 引擎复用现有 `AnalysisAdapter` 协议，每步都通过适配器调用 LLM
- `PromptTaskType` 新增 `GROUPER`、`REACT_STEP`、`REACT_FINALIZE` 三种 task type
- ReAct 最终输出仍为 `AnalysisResponse`，下游报告生成无需改动
- 确定性链构建规则在 react 模式下不调用，但代码保留供 legacy 模式使用
- 所有 ReAct prompt 以 JSON 模板文件存放，支持 profile 切换和 override

### Phase 2 决策
- `source_urls` 从 `ChainEvidenceBundle.source_items` 的 `.url` 字段提取
- URL 在 Markdown 报告中以可点击链接形式呈现
- `NewsItem` 已有 `url` 字段（来自 `RawDocument.url`），无需新增字段

### Phase 1 决策
- CopilotResearchCollector 代码保留，仅 `is_enabled()` 改为读取配置
- 默认 `copilot_research: false`，用户可显式启用
