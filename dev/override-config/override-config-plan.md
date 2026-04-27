# override-config

## 做什么

提供单一 YAML 覆盖文件机制，让用户手动设置每次运行的搜索关键词、数据源子集和 LLM 提示词，无需改动代码或修改全局配置。

## 怎么做

1. 新增 `app/config/override.py`，定义覆盖层类型和加载/合并函数。
2. 扩展 `RunContext`，携带 `OverrideConfig`。
3. 适配各收集器：AkShare 按提供商过滤，Web 替换数据源，Copilot Research 传递搜索关键词。
4. 适配提示词系统：`merge_prompt_overrides()` 合并到 ProfileConfig，渲染后应用消息覆盖。
5. CLI 新增 `--override PATH` 参数。
6. 创建 `config/override.example.yaml` 模板。

## 完成定义

- 通过 `--override` 指定 YAML 即可自定义搜索关键词、数据源、提示词。
- 不指定覆盖文件时行为与改动前完全一致。
- 全量测试通过。

## 依赖

- `source-collection`（收集器接口）
- `llm-analysis`（提示词系统）
