# 开发任务归档索引

> 本文件是 `dev/` 目录的总索引。所有子任务均已完成，此处作为历史归档参考。
> 后续开发工作请参考 `PROJECT_INDEX.md`（代码索引）和 `rule.md`（开发规范）。

---

## 完成状态总览

| # | 子任务 | plan | context | task | 核心产出 |
|---|---|---|---|---|---|
| 1 | project-bootstrap | ✅ | ✅ | ✅ | 项目结构、config、logger、storage 基础 |
| 2 | source-collection | ✅ | ✅ | ✅ | 3 个采集器（akshare/web/copilot_research）+ 缓存 + 重试 |
| 3 | normalization-pipeline | ✅ | ✅ | ✅ | URL/文本去重、时间标准化、可信度评分 |
| 4 | entity-theme-tagging | ✅ | ✅ | ✅ | 11 主题 + 6 实体类型、规则抽取、证据链 |
| 5 | information-chain | ✅ | ✅ | ✅ | 同主题聚合、时序连接、上下游映射、候选链流水线 |
| 6 | llm-analysis | ✅ | ✅ | ✅ | GitHub Models 适配器、prompt 模板、分析引擎 |
| 7 | a-share-mapping | ✅ | ✅ | ✅ | 产业链映射、5 维评分、证据采集 |
| 8 | reporting-output | ✅ | ✅ | ✅ | Markdown/JSON 日报生成、归档管理 |
| 9 | scheduler-automation | ✅ | ✅ | ✅ | 每日调度、批量检测、重试策略 |
| 10 | qa-observability | ✅ | ✅ | ✅ | 错误跟踪、运行日志 |
| 11 | override-config | ✅ | ✅ | ✅ | 运行时配置覆盖机制 |
| 12 | llm-adapter | ✅ | ✅ | ✅ | OpenAI 兼容适配器 |
| 13 | date-filter | ✅ | ✅ | ✅ | 日期范围过滤 |
| 14 | pipeline-refactoring | ✅ | ⚠️ 缺失 | ✅ | ReAct 引擎、采集简化、URL 溯源、双模式切换 |

**说明**：
- `pipeline-refactoring` 缺少 context.md 文件，但 task.md 记录了完整的 5 阶段完成状态
- 每个 `*-plan.md` 记录了任务目标、实现方法、边界和阶段划分
- 每个 `*-context.md` 记录了关键文件、依赖关系、决策记录和进度
- 每个 `*-task.md` 是执行检查清单，全部标记为 `[x]` 完成

---

## 文件命名约定

```
dev/<task-name>/
├── <task-name>-plan.md      # 目标、方案、边界
├── <task-name>-context.md   # 关键文件、依赖、决策记录
└── <task-name>-task.md      # 执行检查清单
```

---

## 后续开发指引

1. **新增功能**：在 `dev/` 下新建子目录，遵循上述命名约定
2. **修改现有模块**：参考对应 `*-context.md` 了解依赖和决策背景
3. **技术债修复**：参见 `PROJECT_INDEX.md` 第 7 节"已知问题与技术债"
4. **开发规范**：参见 `rule.md`
