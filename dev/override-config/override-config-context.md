# override-config

## 关键文件

- `app/config/override.py`（新建）— `OverrideConfig`、`SourcesOverrideConfig`、`WebSourceOverride`、`TaskPromptOverride`、`PromptOverrideConfig`、`load_override()`、`apply_override()`
- `app/config/__init__.py`（更新）— 导出覆盖层类型
- `app/collectors/base.py`（更新）— `RunContext` 新增 `override` 字段
- `app/collectors/akshare_collector.py`（更新）— 按 `akshare_providers` 过滤提供商
- `app/collectors/web_collector.py`（更新）— 覆盖数据源替换
- `app/collectors/copilot_research_collector.py`（更新）— `ResearchRequest` 新增 `search_keywords`
- `app/analysis/prompts/profile.py`（更新）— 新增 `merge_prompt_overrides()`
- `app/analysis/prompts/file_system_renderer.py`（更新）— 渲染后应用消息覆盖 + `search_keywords_json` 上下文变量
- `app/analysis/engine.py`（更新）— 接受 `search_keywords` 和 `profile_config`
- `app/main.py`（更新）— `--override` CLI + 加载/合并/传播
- `config/override.example.yaml`（新建）— 覆盖文件模板
- `tests/test_override.py`（新建）— 30 个测试

## 决策记录

- 使用单一 YAML 覆盖文件（非按日期），通过 `--override` 指定路径。
- 覆盖文件所有字段可选，缺省走默认逻辑。
- 优先级：覆盖 YAML > CLI 参数 > config.yaml 默认值。
- AkShare 提供商通过过滤 `_PROVIDERS` 实现，不修改类属性。
- Web 数据源通过替换 `self._sources` 的遍历对象实现，不修改实例状态。
- 提示词覆盖通过 `TaskTemplateMapping.overrides` dict 传递，渲染后修改消息内容。
- `search_keywords_json` 作为模板变量注入，现有模板不引用则无影响。

## 环境 / 配置假设

- 覆盖文件格式为 YAML，可安全提交到版本控制（不含敏感信息）。

## 当前进度

- ✅ 新建 `app/config/override.py`，定义全部覆盖层数据类与加载/合并函数
- ✅ 扩展 `RunContext`，新增 `override: OverrideConfig | None = None`
- ✅ 适配 AkShareCollector：按 `akshare_providers` 过滤
- ✅ 适配 WebCollector：覆盖数据源替换
- ✅ 适配 CopilotResearchCollector：`ResearchRequest` 新增 `search_keywords`
- ✅ 适配提示词系统：`merge_prompt_overrides()` + 渲染后消息覆盖 + `search_keywords_json`
- ✅ CLI 新增 `--override PATH` 参数
- ✅ 创建 `config/override.example.yaml`
- ✅ 编写测试 `tests/test_override.py`（30 个测试）
- ✅ 全量测试 1674/1674 通过

## override-config 阶段已完成！
