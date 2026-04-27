# date-filter

## 关键文件

- `app/normalize/date_filter.py`（新建）— `filter_by_date_range()`、`filter_last_n_days()`
- `app/normalize/__init__.py`（更新）— 导出 date_filter 函数
- `app/config/schema.py`（更新）— `SourcesConfig` 新增 `date_filter_days: int = 7`
- `app/config/loader.py`（更新）— 解析 `date_filter_days`
- `app/config/override.py`（更新）— `SourcesOverrideConfig` 新增 `date_filter_days`
- `app/main.py`（更新）— dry-run 显示 `date_filter_days`
- `config.yaml`（更新）— 新增 `date_filter_days: 7`
- `config/override.example.yaml`（更新）— 新增 `date_filter_days` 示例
- `tests/test_date_filter.py`（新建）— 15 个测试

## 决策记录

- 过滤发生在**时间归一化之后**，此时日期已保证为 `YYYY-MM-DD` 格式。
- 过滤发生在**去重和可信度评分之前**，避免浪费计算在过期条目上。
- 默认保留近 7 天（含当天），即 `[today - 6, today]` 范围。
- `filter_last_n_days(n=7)` 的范围是 `[today - n + 1, today]`，所以 n=7 时从 7 天前开始。
- 日期为空或无法解析的条目被静默丢弃。
- 保留的条目在 `metadata["date_filter"]` 中记录过滤信息（start_date、end_date、kept=True）。
- `date_filter_days` 可通过 override YAML 覆盖，方便临时扩大/缩小搜索范围。

## 环境 / 配置假设

- 默认 7 天回看窗口，适合日度投资新闻场景。
- 可通过 `config.yaml` 或 `--override` 调整。

## 当前进度

- ✅ 新建 `app/normalize/date_filter.py`
- ✅ 更新 `app/normalize/__init__.py` 导出
- ✅ 新增 `SourcesConfig.date_filter_days`
- ✅ 更新 loader 解析 `date_filter_days`
- ✅ 更新 `OverrideConfig` 支持 `date_filter_days` 覆盖
- ✅ 更新 dry-run 显示
- ✅ 更新 config.yaml 和 override.example.yaml
- ✅ 编写 15 个测试
- ✅ 全量测试 1689/1689 通过

## date-filter 阶段已完成！
