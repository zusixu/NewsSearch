# project-bootstrap

## 做什么

搭建项目最小可运行骨架，明确 Python 入口、配置加载、日志、SQLite、目录结构，以及 `quant` 环境下的运行约定。

## 怎么做

1. 初始化 `app/`、`scripts/`、`data/`、`tests/` 基础目录。
2. 建立统一 CLI 入口，支持 `run`、`collect-only`、`analyze-only`、`dry-run`。
3. 建立配置加载机制，固定支持 `.env + YAML`。
4. 建立日志与 SQLite 初始化逻辑。
5. 固化 `conda activate quant` 的运行说明与脚本包装。

已确认：
- Python 包管理与运行环境固定使用本地 conda 的 `quant` 环境；
- 配置格式固定为 `.env + YAML`，不再作为待定项。

## 完成定义

- 项目目录可直接运行主命令。
- 配置、日志、数据库路径均可正常初始化。
- 后续模块可在此骨架上继续接入。

## 依赖

- 无前置代码依赖。
