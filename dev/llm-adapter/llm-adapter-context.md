# llm-adapter

## 关键文件

- `app/analysis/adapters/openai_compatible.py`（新建）— `OpenAICompatibleAdapter`、`OpenAICompatibleConfig`、`MissingAPIKeyError`、`OpenAICompatibleAPIError`
- `app/analysis/adapters/__init__.py`（更新）— 导出 OpenAI 兼容适配器类型
- `app/analysis/engine.py`（更新）— 当 `llm_endpoint` 非空时选用 OpenAI 兼容适配器
- `app/config/schema.py`（更新）— 新增 `LLMConfig`（endpoint / model_id / api_key_env_var），`AppConfig` 新增 `llm` 和 `llm_api_key`
- `app/config/loader.py`（更新）— 解析 `llm` section + `LLM_API_KEY` 环境变量
- `app/config/__init__.py`（更新）— 导出 `LLMConfig`
- `app/main.py`（更新）— 传递 LLM 配置到引擎，dry-run 显示 LLM 信息
- `config.yaml`（更新）— 新增 `llm` section
- `.env`（新建）— `LLM_API_KEY`
- `.env.example`（更新）— 新增 `LLM_API_KEY`

## 决策记录

- 使用通用 `OpenAICompatibleAdapter` 而非火山引擎专用适配器，保持兼容性。
- API Key 优先级：`config.api_key` 直接设置 > `api_key_env_var` 环境变量。
- 适配器选择逻辑：`llm.endpoint` 非空 → OpenAI 兼容；否则 → GitHub Models（向后兼容）。
- 默认模型改为 `deepseek-v4-flash`。

## 环境 / 配置假设

- 端点：`https://ark.cn-beijing.volces.com/api/v3/chat/completions`
- 模型：`deepseek-v4-flash`
- API Key 存储在 `.env` 的 `LLM_API_KEY` 中。

## 当前进度

- ✅ 新建 `OpenAICompatibleAdapter`
- ✅ 新增 `LLMConfig`，更新 `AppConfig` 和 loader
- ✅ 更新 `AnalysisEngine` 自动选择适配器
- ✅ 更新 `config.yaml` 和 `.env`
- ✅ 更新 `app/main.py` 传递 LLM 配置
- ✅ 全量测试 1674/1674 通过

## llm-adapter 阶段已完成！
