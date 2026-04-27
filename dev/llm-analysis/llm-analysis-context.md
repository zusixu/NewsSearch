# llm-analysis

## 关键文件

- `app/analysis/adapters/contracts.py`（已创建）— 所有 frozen dataclass 合约与 `AnalysisAdapter` Protocol
- `app/analysis/adapters/github_models.py`（已创建）— GitHub Models 适配器实现（`GitHubModelsAdapter`、`GitHubModelsConfig`、`PromptRenderer`、`ChatMessage`、错误类）
- `app/analysis/adapters/__init__.py`（已更新）— 导出所有公开名称（含新增的 github_models 符号）
- `app/analysis/__init__.py`（已更新）— 顶层 re-export（含 github_models 与 prompts 符号）
- `app/analysis/prompts/file_system_renderer.py`（已更新）— `FileSystemPromptRenderer`、模板加载与渲染、模板异常定义，支持 profile 配置
- `app/analysis/prompts/profile.py`（已创建）— prompt profile 加载与管理（`PromptProfileConfig`、`PromptProfileLoader`、`TaskTemplateMapping`、错误类）
- `app/analysis/prompts/templates/`（已创建）— 三类任务默认模板：`summary.json`、`chain_completion.json`、`investment_ranking.json`
- `app/analysis/prompts/__init__.py`（已更新）— prompts 包导出（含新增的 profile 管理符号）
- `config/prompt_profiles/default.yaml`（已创建）— 默认 prompt profile 配置文件
- `tests/test_analysis_adapter_contracts.py`（已创建）— 39 个专项测试
- `tests/test_github_models_adapter.py`（已创建）— 13 个专项测试
- `tests/test_filesystem_prompt_renderer.py`（已创建）— prompt 模板与渲染器专项测试
- `tests/test_prompt_profile.py`（已创建）— prompt profile 专项测试（21 个测试）
- `config.yaml`（已更新）— 更新 prompt 配置，新增 `profiles_dir` 和 `templates_dir`
- `app/config/schema.py`（已更新）— 更新 `PromptConfig` 以包含 `templates_dir`
- `app/config/loader.py`（已更新）— 修复 `_build_prompt` 函数，增加 `templates_dir` 加载
- `app/main.py`（已更新）— 增加 `--prompt-profile` CLI 参数，集成完整分析流程
- `app/analysis/engine.py`（已创建）— 分析引擎 `AnalysisEngine`、dry-run 适配器 `DryRunAnalysisAdapter`
- `app/storage/database.py`（已更新）— 新增 `RunLogStore`、`PromptProfileStore`、`ChainScoreStore`、`InfoChainStore`
- `app/storage/schema.sql`（已更新）— 扩展 `run_logs`、`chain_scores` 表，新增 `prompt_profiles` 表
- `tests/test_prompt_profile.py`（已创建）— prompt profile 专项测试（21 个测试）
- `tests/test_prompt_version_tracking.py`（已创建）— prompt 版本记录专项测试（13 个测试）
- `tests/test_analysis_engine.py`（已创建）— 分析引擎专项测试（13 个测试）
- `config/prompt_profiles/default.yaml`（已创建）— 默认 prompt profile 配置

## 决策记录

- 模型入口优先使用 GitHub Models / 可编程 API。
- Prompt 必须支持人工修改。
- 需要保留 prompt profile 与运行记录之间的关联。
- **Adapter 层设计**：使用 `frozen=True` dataclass（全部值对象）+ `@runtime_checkable` Protocol（`AnalysisAdapter`）。
- **三类分析任务**通过 `PromptTaskType` 枚举区分：`SUMMARY`（摘要归纳）、`CHAIN_COMPLETION`（链路补全）、`INVESTMENT_RANKING`（投资排序）。
- `PromptProfile` 是唯一的人工调整入口（`profile_name` + `version`），实现层必须以此选择 prompt 模板。
- `AnalysisInput` 直接持有 `InformationChain` + `ChainEvidenceBundle` 引用，不拷贝，与 information-chain 层零耦合。
- `AnalysisAdapter` Protocol 方法签名为 `analyse(AnalysisInput) -> AnalysisResponse`，与具体 provider 无关。
- **GitHub Models API 决策**：
  - 官方端点：`POST https://models.github.ai/inference/chat/completions`
  - 必要 Headers：`Accept: application/vnd.github+json`、`Authorization: Bearer <token>`、`X-GitHub-Api-Version: 2022-11-28`、`Content-Type: application/json`
  - PAT 需要 `models` scope；从环境变量读取（默认 `GITHUB_TOKEN`）。
  - `response_format: {type: "json_object"}` 强制 JSON 输出。
  - 仅用 stdlib `urllib`，不引入额外依赖。
  - 使用 `_open_func` 可注入 HTTP 层，完全可 mock。
- **`PromptRenderer` Protocol**：`render(AnalysisInput) -> list[ChatMessage]`；注入式设计，node 3 直接插入文件系统实现，无需改动本适配器。
- **Prompt 模板实现决策**：
  - 模板格式使用 JSON，仅依赖 stdlib，便于人工编辑与版本管理；
  - 默认模板目录固定在 `app/analysis/prompts/templates/`；
  - 由 `FileSystemPromptRenderer` 按 `PromptTaskType` 选择模板并渲染；
  - 模板中的示例 JSON 结构使用转义花括号，避免与 `str.format(...)` 占位符冲突；
  - 删除了未被引用的旧 `renderer.py` 和重复模板文件，保留单一来源实现。
- **Prompt profile 实现决策**：
  - Profile 配置文件使用 YAML 格式，便于人工编辑和版本管理；
  - Profile 配置目录固定在 `config/prompt_profiles/`；
  - 每个 profile 是独立的 YAML 文件，文件名与 profile_name 一致；
  - Profile 配置包含 `profile_name`、`version`、`description` 和 `tasks` 映射；
  - `tasks` 映射为每个 `PromptTaskType` 指定模板文件名和可选的覆盖配置；
  - `PromptProfileLoader` 负责加载和验证 profile 配置；
  - `FileSystemPromptRenderer` 可以接受 `PromptProfileConfig` 来选择模板；
  - 保持向后兼容，没有 profile 配置时仍使用默认模板映射。
- **LLM 响应 JSON 结构约定**（由 prompt 模板决定，node 3 实现时必须与此一致）：
  ```json
  {
    "chain_results": [
      {"chain_id": "...", "summary": "...", "completion_notes": "...", "key_entities": [...], "confidence": 0.0}
    ],
    "ranking": {
      "entries": [
        {"chain_id": "...", "rank": 1, "score": 0.0, "rationale": "..."}
      ]
    }
  }
  ```
- **命令行切换 profile 决策**：
  - 在 `app/main.py` 中添加 `--prompt-profile` 参数，可覆盖 `config.yaml` 中的 `prompt.default_profile`；
  - `app/main.py` 的所有模式（`dry-run`/`run`/`collect-only`/`analyze-only`）都接受该参数；
  - Profile 加载错误会给出友好提示，不会导致程序崩溃。
- **Prompt 版本记录决策**：
  - 扩展 `run_logs` 表，新增 `prompt_profile_name`、`prompt_profile_version`、`prompt_profile_desc` 字段；
  - 扩展 `chain_scores` 表，新增 `prompt_profile_name`、`prompt_profile_version` 字段；
  - 新增 `prompt_profiles` 表，用于完整归档 prompt profile 配置和模板内容；
  - 新增 `RunLogStore`、`PromptProfileStore` 存储类，管理运行日志和 profile 归档；
  - 每次运行开始时记录 profile 信息，结束时更新完成状态。
- **结构化分析结果输出决策**：
  - 创建 `app/analysis/engine.py`，实现 `AnalysisEngine` 协调完整分析流程；
  - 实现 `DryRunAnalysisAdapter`，用于 dry-run 模式（无需真实 LLM 调用）；
  - 分析流程：`TaggedOutput` → `InformationChain` → `AnalysisInput` → `AnalysisResponse`；
  - 新增 `ChainScoreStore`、`InfoChainStore` 管理链评分和信息链的存储；
  - `app/main.py` 的 `run` 和 `analyze-only` 模式集成分析引擎，`dry-run` 模式完整测试分析流程。

## 环境 / 配置假设

- `GITHUB_TOKEN`：GitHub PAT，需 `models` scope（可通过 `GitHubModelsConfig.token_env_var` 覆盖）。
- 默认模型：`GitHubModelsConfig` 构造时由调用方指定 `model_id`（无硬编码默认模型）。
- 默认超时：60 秒；默认 API 版本：`2022-11-28`。

## 当前进度

- ✅ 第 1 步：定义 analysis adapter 接口（frozen dataclass + Protocol），39 个测试全部通过。
- ✅ 第 2 步：接入 GitHub Models（`GitHubModelsAdapter` + 可注入 `PromptRenderer` + 配置层），13 个测试全部通过。
- ✅ 第 3 步：建立 prompt 模板目录。
  - 已完成 `FileSystemPromptRenderer`，默认从 `app/analysis/prompts/templates/` 加载模板；
  - 已为 `SUMMARY`、`CHAIN_COMPLETION`、`INVESTMENT_RANKING` 建立默认 JSON 模板；
  - 已将 prompts 相关公开符号从 `app.analysis` 与 `app.analysis.prompts` 暴露；
  - 已清理重复的旧 prompt 实现与重复模板；
  - `tests/test_filesystem_prompt_renderer.py` 已覆盖导入面、模板映射、渲染内容、确定性输出与异常路径。
- ✅ 第 4 步：建立 prompt profile 机制。
  - 已在 `config/prompt_profiles/` 目录设计 YAML 格式的 profile 配置文件；
  - 已创建默认 profile `config/prompt_profiles/default.yaml`；
  - 已在 `app/analysis/prompts/profile.py` 建立 profile 读取与解析层；
  - 已定义 `TaskTemplateMapping`、`PromptProfileConfig`、`PromptProfileLoader` 等数据类与加载器；
  - 已更新 `FileSystemPromptRenderer` 以支持通过 `PromptProfileConfig` 选择模板；
  - 已更新 `config.yaml` 中的 prompt 配置，分离 `profiles_dir` 和 `templates_dir`；
  - 已编写完整的测试文件 `tests/test_prompt_profile.py`（21 个测试全部通过）；
  - 当前全量测试：`pytest tests\ -q` **1391/1391** 通过。
- ✅ 第 5 步：支持命令行切换 prompt profile。
  - 已修复 `app/config/loader.py` 中的 `_build_prompt` 函数，添加缺失的 `templates_dir` 加载；
  - 已在 `app/main.py` 中增加 `--prompt-profile` 参数，可覆盖配置文件中的默认值；
  - 已更新所有模式的处理函数，支持 profile 配置的传递和显示；
  - 已添加错误处理，当 profile 不存在时有友好的错误提示；
  - 当前全量测试通过。
- ✅ 第 6 步：记录运行使用的 prompt 版本。
  - 已扩展 `app/storage/schema.sql` 中的 `run_logs` 表，新增 `prompt_profile_name`、`prompt_profile_version`、`prompt_profile_desc` 字段；
  - 已扩展 `chain_scores` 表，新增 `prompt_profile_name`、`prompt_profile_version` 字段；
  - 已新增 `prompt_profiles` 表，用于完整归档 prompt profile 配置和模板内容；
  - 已新增 `RunLogEntry`、`RunLogStore`、`PromptProfileStore` 数据类和存储类；
  - 已编写测试文件 `tests/test_prompt_version_tracking.py`（13 个测试全部通过）；
  - 当前全量测试通过。
- ✅ 第 7 步：输出结构化分析结果。
  - 已在 `app/analysis/engine.py` 中实现 `AnalysisEngine` 分析引擎，协调整个分析流程；
  - 已实现 `DryRunAnalysisAdapter`，无需真实 LLM 的 dry-run 适配器；
  - 已实现完整流程：`TaggedOutput` → `InformationChain` → `AnalysisInput` → `AnalysisResponse`；
  - 已新增 `ChainScoreEntry`、`ChainScoreStore`、`InfoChainStore` 数据类和存储类；
  - 已更新 `app/main.py` 的 `run` 和 `analyze-only` 模式，调用分析引擎；
  - 已确保与 `RunLogStore` 和 `PromptProfileStore` 集成；
  - 已编写测试文件 `tests/test_analysis_engine.py`（13 个测试全部通过）；
  - 当前全量测试：`pytest tests\ -q` **1417/1417** 通过。

## llm-analysis 阶段已完成！

llm-analysis 的所有 7 个 checklist 节点已全部完成。

## 下一步推荐执行点

- llm-analysis 已全部完成；
- 推荐下一个顶级子任务：**a-share-mapping**（A股映射），将事件链映射到 A 股板块、产业环节、公司类型或候选标的池；
- 或下一个：**reporting-output**（报告输出），生成每日 Top 10 Markdown/JSON 报告。

## 交接要求

- 上下文快用完时，先回写当前进度、修改文件、阻塞项和下一步，再切换新的子智能体。

