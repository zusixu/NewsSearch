# llm-analysis

## 做什么

接入 GitHub Models / 可编程 API，完成摘要归纳、链路补全、投资排序，并保留可人工调整的 prompt 入口。

## 怎么做

1. 实现统一 `analysis_adapter`。
2. 将 prompt 从代码中解耦为模板文件。
3. 支持多套 prompt profile。
4. 支持运行时选择或覆盖 prompt profile。
5. 记录每次运行使用的 prompt 版本。

## 完成定义

- 模型调用链路打通。
- Prompt 可独立编辑，不需要改主代码。
- 分析结果可返回结构化摘要、链路推理和排序说明。

## 依赖

- `information-chain`
