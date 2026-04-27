# llm-adapter

## 做什么

接入 OpenAI 兼容格式的大模型 API（火山引擎 / Ark），替换默认的 GitHub Models 适配器。

## 怎么做

1. 新增 `OpenAICompatibleAdapter`，使用标准 `Authorization: Bearer` 头，支持任意 OpenAI 兼容端点。
2. 在 `config.yaml` 中新增 `llm` section（endpoint / model_id / api_key_env_var）。
3. 在 `AppConfig` 中新增 `LLMConfig` 和 `llm_api_key`。
4. 在 `AnalysisEngine` 中，当 `llm_endpoint` 非空时自动选用 OpenAI 兼容适配器。
5. 在 `.env` 中配置 API Key。

## 完成定义

- `config.yaml` 中配置 endpoint 后，dry-run 显示 `adapter=openai_compatible`。
- API Key 从 `.env` 加载，不在 YAML 中明文存储。
- 全量测试通过。

## 依赖

- `llm-analysis`（适配器框架）
