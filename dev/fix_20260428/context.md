# Context — 技术债修复 2026-04-28

## 背景

MM 项目（Daily AI Investment News Pipeline）已完成核心功能开发，代码库约 12,000 行 Python、52 个测试文件。`PROJECT_INDEX.md` §7 列出 14 项已知技术债（#2–#14），`rule.md` §11 定义了优先修复路线。

本次修复任务覆盖全部 14 项技术债，按依赖关系拆分为 8 个可并行执行的子任务。

## 项目约束

- **环境**：Windows 10/11, Conda `quant` 环境 (Python 3.11)
- **测试**：`pytest tests/ -q`，52 个文件全量回归
- **数据模型**：`frozen=True` dataclass，不修改输入
- **分层规则**：上层→下层单向，storage 不得依赖 analysis
- **日志规范**：所有网络 I/O 必须日志，禁止 `except Exception: pass`
- **最小变更**：只改需要改的，不顺手重构

## 技术债清单摘要

| # | 问题 | 严重度 | 关键文件 |
|---|------|--------|----------|
| 2 | 关系类型覆盖级联 | 中 | `app/chains/candidate_generation.py` |
| 3 | ReAct duck-typing | 中 | `app/analysis/react/engine.py:578-634` |
| 4 | web_access_transport 无日志 | 高 | `app/collectors/web_access_transport.py` |
| 5 | 时效性评分硬编码 80 | 低 | `app/mapping/engine.py:613-623` |
| 6 | use_profile 死代码 | 低 | `app/analysis/engine.py:337-338` |
| 7 | ReAct 工具 2/3 为 stub | 中 | `app/analysis/react/tools.py` |
| 8 | 存储层依赖分析层 | 中 | `app/storage/database.py:30-32` |
| 9 | apply_override 不完整 | 中 | `app/config/override.py` |
| 10 | ranking/ 空模块 | 低 | `app/ranking/__init__.py` |
| 11 | 适配器解析重复 | 低 | `github_models.py`, `openai_compatible.py` |
| 12 | ChatMessage/PromptRenderer 位置不当 | 低 | `github_models.py` |
| 13 | CDP proxy 硬编码 sleep | 低 | `web_access_transport.py:176,189` |
| 14 | ReAct finalize 吞异常 | 中 | `react/engine.py:499` |

## 关键代码调研发现

### web_access_transport.py (#4, #13)
- 15+ 处静默吞异常
- CDPProxyClient 7 个方法均无日志
- WebAccessTransport 6 个方法均无日志
- 4 个搜索后端降级无日志
- `time.sleep(2)` (行176), `time.sleep(3)` (行189) 无日志说明

### 关系类型覆盖级联 (#2)
- `same_topic_grouping.py:110` → SAME_TOPIC
- `temporal_connection.py:73` → TEMPORAL (覆盖 SAME_TOPIC)
- `upstream_downstream.py:143` → UPSTREAM_DOWNSTREAM (覆盖 TEMPORAL)
- 下游消费者：prompt 渲染器使用 `relation_to_prev.value`，mapping/reports 不使用

### ReAct duck-typing (#3)
- `_call_llm_raw` 访问: `_render_messages`, `_build_payload`, `_read_token`/`_read_api_key`, `_post`
- 这些方法不在 AnalysisAdapter Protocol 中
- 新适配器必须实现相同的私有方法签名

### 存储层分层违规 (#8)
- `database.py:30-32` 导入: `PromptTaskType`, `PromptProfileConfig`, `PromptProfileLoader`, `TaskTemplateMapping`
- 用于 PromptProfileStore 的 CRUD 操作

### apply_override (#9)
- 解析但不回写的字段: `search_keywords`, `web_sources`, `prompt_overrides`, `akshare_providers`
- 需确认 AppConfig schema 中对应字段

### 适配器解析重复 (#11)
- `github_models.py:324-403` 和 `openai_compatible.py:266-335`
- 共享: code-fence 剥离 → JSON 解析 → chain_results 提取 → ranking 提取 → AnalysisResponse 构建

### 死代码
- `news_item.py:51-52` 空 TYPE_CHECKING 块
- `date_filter.py:28` 未使用 `import copy`
- `entity_types.py:25` 未使用 `Optional`
- `engine.py:337-338` use_profile 死代码
