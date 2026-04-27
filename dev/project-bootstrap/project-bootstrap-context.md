# project-bootstrap

## 关键文件

- `app/main.py`
- `app/config/` — 配置加载模块（已完成）
  - `app/config/__init__.py` — 公共 API 导出（新增 `LoggingConfig` 导出）
  - `app/config/schema.py` — 类型化 dataclass 定义（新增 `LoggingConfig`；`AppConfig` 新增 `logging` 字段；`validate()` 新增 level/log_dir 校验）
  - `app/config/loader.py` — 新增 `_build_logging()` builder；`load_config()` 传入 `logging=_build_logging(raw)`
- `config.yaml` — 新增 `logging:` 节（`log_dir: data/logs`，`level: INFO`）
- `app/logger/` — 日志模块（已完成）
  - `app/logger/__init__.py` — 公共 API：`setup_logging`、`get_logger`
  - `app/logger/formatter.py` — `JSONFormatter`（NDJSON，UTC ISO-8601 时间戳，支持 extra 字段合并）
  - `app/logger/setup.py` — `setup_logging(cfg: LoggingConfig)`：创建目录、安装文件 handler（JSON、每日轮转、保留 30 天）和控制台 handler（可读格式）；幂等设计，重复调用不会重复添加 handler
- `tests/test_logger.py` — 20 个测试（JSONFormatter、setup_logging、get_logger、LoggingConfig 校验）
- `app/storage/`（已完成）
  - `app/storage/schema.sql` — 基准 DDL（8 张表 + 19 个索引，全部 IF NOT EXISTS，幂等）
  - `app/storage/database.py` — `open_connection` / `init_db` / `get_db` 三个公共帮助函数
  - `app/storage/__init__.py` — 公共 API 导出
- `scripts/bootstrap.ps1`（已完成）

## 决策记录

- 日志模块包名使用 `app/logger/`（非 `app/logging/`），避免与标准库 `logging` 模块命名冲突。
- 文件日志使用 NDJSON（每条一行 JSON），便于后续日志聚合与可观测性；控制台日志使用人类可读格式，便于开发调试。
- 日志 handler 通过自定义属性 `_mm_handler=True` 标记，实现 `setup_logging` 幂等重入而不积累重复 handler。
- `LoggingConfig` 的 `log_dir` 和 `level` 均通过 `AppConfig.validate()` 校验，与其他配置节保持一致的错误处理风格。
- `logging` YAML 节扩展了 `config.yaml` 和 `schema.py`/`loader.py`；不影响已有字段，向后兼容。
- 默认运行环境为本地 `conda` 的 `quant` 环境。
- 数据库优先使用 SQLite。
- 配置格式固定为 `.env + YAML`。
- 配置加载不依赖 python-dotenv；使用标准库手动解析 `.env`，PyYAML 加载 YAML。
- `.env` 文件中的 toonfigError`，不做静默回 退。

## 当前进度（project-bootstrap 全部完成 ✅）

- [x] 创建基础目录结构（已完成）
  - 创建了所有 Python 包目录并写入空 `__init__.py`：
    `app/`, `app/config/`, `app/collectors/`, `app/normalize/`,
    `app/entity/`, `app/chains/`, `app/analysis/`, `app/analysis/adapters/`,
    `app/ranking/`, `app/reports/`, `app/storage/`, `app/scheduler/`
  - 为三个 collector 创建了占位文件：
    `app/collectors/akshare_collector.py`,
    `app/collectors/web_collector.py`,
    `app/collectors/copilot_research_collector.py`
  - 为空数据目录添加 `.gitkeep`：
    `data/raw/`, `data/db/`, `data/reports/`, `scripts/`,
    `app/analysis/prompts/`
  - 创建了 `tests/__init__.py`
  - 创建了 `.env.example`（含 GITHUB_TOKEN / AKSHARE_TOKEN 占位注释）

- [x] 建立主运行入口（已完成）
  - 创建了 `app/main.py`
  - 支持四种 CLI 模式：`run`、`collect-only`、`analyze-only`、`dry-run`
  - 支持 `--date YYYY-MM-DD` 和 `--prompt-profile PROFILE` 参数
  - 每个模式对应独立 stub handler，结构准备好接收后续模块实现
  - 遵循 `ModeHandler` Protocol，类型安全
  - 退出码：成功=0，运行时错误=1，参数非法=2（argparse 默认）
  - 已验证：`python -m app.main <mode>` 正常输出；非法 mode 退出码为 2

- [x] 建立配置加载模块（已完成）
  - 新建 `app/config/schema.py`：AppConfig + 5 个 Section dataclass + ConfigError
  - 新建 `app/config/loader.py`：_parse_dotenv / _inject_env / _load_yaml_file / load_config
  - 更新 `app/config/__init__.py`：公共 API 导出
  - 新建 `config.yaml`（项目根）：含 sources / scheduler / prompt / storage / output 默认值
  - 新建 `tests/test_config.py`：26 个测试全部通过
  - 字段设计对齐 plan.md：copilot_research 强制参与、双次调度（08:30/14:00）、A 股优先输出目录

- [x] 建立日志模块（已完成）
  - 新建 `app/logger/__init__.py`：公共 API（`setup_logging`、`get_logger`）
  - 新建 `app/logger/formatter.py`：`JSONFormatter`（NDJSON，UTC ISO-8601，extra 字段合并，异常 traceback 支持）
  - 新建 `app/logger/setup.py`：`setup_logging(cfg)` — 创建目录、安装文件 handler（JSON 每日轮转保留 30 天）+ 控制台 handler（可读格式）；幂等
  - 扩展 `app/config/schema.py`：新增 `LoggingConfig` dataclass；`AppConfig` 新增 `logging` 字段；`validate()` 新增 level/log_dir 校验
  - 扩展 `app/config/loader.py`：新增 `_build_logging()` builder
  - 扩展 `app/config/__init__.py`：导出 `LoggingConfig`
  - 扩展 `config.yaml`：新增 `logging:` 节（`log_dir: data/logs`，`level: INFO`）
  - 新建 `tests/test_logger.py`：20 个测试全部通过
  - 全量测试：46 个测试全部通过

- [x] 建立 SQLite 初始化逻辑（已完成）
  - 新建 `app/storage/schema.sql`：8 张表（run_logs / raw_documents / news_items / entities / news_entity_links / info_chains / chain_evidence / chain_scores）+ 19 个索引；所有 DDL 使用 IF NOT EXISTS，幂等
  - 新建 `app/storage/database.py`：`open_connection(db_path)` — 仅打开连接并设置 pragmas；`init_db(db_path)` — 打开 + 应用 schema；`get_db` 为 `init_db` 别名；自动创建父目录；支持 `:memory:` 内存库
  - 更新 `app/storage/__init__.py`：导出三个公共帮助函数
  - 新建 `tests/test_storage.py`：25 个测试全部通过（schema 资产、连接帮助函数、幂等性、表/索引完整性、约束验证）
  - 全量测试：71 个测试全部通过（含前序 config/logger 测试）

- [x] 建立基础运行脚本（已完成）
  - 新建 `scripts/bootstrap.ps1`：PowerShell 包装脚本，在 `quant` conda 环境中无需手动激活直接运行 `python -m app.main`
  - 支持所有 CLI 模式（`run` / `collect-only` / `analyze-only` / `dry-run`）及 `--date` / `--prompt-profile` 参数
  - 自动定位 conda（优先 `CONDA_EXE` 环境变量，次查 PATH，再查常用安装路径）
  - conda 不可用或 `quant` 环境不存在时输出明确错误并以非零退出码退出
  - 使用 `conda run --no-capture-output --live-stream` 保持实时输出，兼容 Task Scheduler 等非交互上下文
  - bootstrap 级别：不含调度注册、重试、每日编排逻辑（留给 scheduler-automation 子任务）

- [x] 补充启动说明（已完成）
  - 新建 `README.md`（项目根）：面向开发者的启动说明，严格限定于当前 bootstrap 范围
  - 涵盖：`quant` conda 环境创建、`.env.example` 复制与填写、`config.yaml` 关键配置节说明
  - 涵盖：两种运行方式（`scripts\bootstrap.ps1` 推荐 / `python -m app.main` 直接）
  - 涵盖：全量及按模块的 `pytest` 命令（预期 71 个测试全通过）
  - 涵盖：关键文件树一览，明确标注尚未实现的功能

## project-bootstrap 完成状态

**所有 7 项 checklist 条目已全部完成。** project-bootstrap 子任务正式收尾。

## 下一步（交接给下一个子任务）

下一个子任务：**source-collection**（数据采集自动化）

建议起点：
1. 阅读 `plan.md` 中 source-collection 相关章节，了解采集目标（AkShare、web/RSS、Copilot research）
2. 在 `app/collectors/` 下实现三个 collector 的实际逻辑（当前为占位文件）
3. 将 `app/main.py` 中 `_handle_collect_only` 的 stub 替换为真实调用
4. 补充 `tests/test_collectors.py`

前置依赖已全部就绪：config loader、logging、SQLite init、CLI entry point、bootstrap.ps1 均已稳定。

