# date-filter

## 做什么

为搜索/收集流程添加日期范围过滤，默认只保留近 7 天的数据，自动丢弃过期条目。

## 怎么做

1. 新增 `app/normalize/date_filter.py`，实现 `filter_by_date_range()` 和 `filter_last_n_days()`。
2. 在 `config.yaml` 的 `sources` section 新增 `date_filter_days` 配置项。
3. 在 `SourcesConfig` 新增 `date_filter_days` 字段，默认 7。
4. 在 `OverrideConfig` 的 `SourcesOverrideConfig` 新增 `date_filter_days`，支持覆盖。
5. dry-run 模式显示 `date_filter_days` 配置。

## 完成定义

- 收集的 NewsItem 经过时间归一化后，按 `date_filter_days` 过滤掉过期条目。
- 过滤阈值可通过 config.yaml 和 override YAML 配置。
- 全量测试通过。

## 依赖

- `normalization-pipeline`（时间归一化 stage，date_filter 需在其后执行）
