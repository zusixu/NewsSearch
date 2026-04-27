# reporting-output

## 关键文件

- `app/reports/core.py` - 主要的报告生成逻辑
- `app/reports/__init__.py` - 模块导出
- `tests/test_reports.py` - 完整的测试套件
- `data/reports/` - 报告输出目录（运行时创建）

## 决策记录

- Markdown 面向人工阅读 - 实现了美观的排版和易于阅读的格式
- JSON 面向 AI/程序二次处理 - 包含完整的结构化数据
- 日报需可回溯到证据和 prompt profile - 在头部包含了 prompt profile 和版本信息
- 多批次支持 - 支持 "pre-market"（开盘前）和 "midday"（午间）两个批次
- 历史归档结构 - 按年份/月份/日期组织报告文件
- 风险提示 - 包含置信度提示、估值提示等多种风险类型

## 数据结构说明

### DailyReport
完整的日报对象，包含：
- header: 日报头部信息
- top_chains: Top 10 信息链列表
- risk_warnings: 风险提示列表
- summary: 日报总览摘要

### DailyReportChainEntry
单条信息链条目，包含：
- chain_id: 信息链 ID
- rank: 排名（1-based）
- title: 标题
- summary: 摘要（来自 LLM 分析）
- confidence: 置信度（0-1）
- rationale: 排名理由
- a_share_mapping: A 股映射结构
- a_share_score: A 股可映射性评分（可选）
- with_evidence: 带旁证的映射（可选）
- chain_analysis: 完整的链分析结果（可选）

### RiskWarning
风险提示对象，包含：
- risk_type: 风险类型（置信度提示、估值提示、时效性提示、反证提示、其他风险）
- severity: 严重程度（high/medium/low）
- message: 风险提示内容
- related_chain_id: 关联的信息链 ID（可选）
- related_stock_code: 关联的股票代码（可选）

## 当前进度

已全部完成并通过所有测试！

## 下一步

（此阶段已完成）
