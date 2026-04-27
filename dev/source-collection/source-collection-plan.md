# source-collection

## 做什么

实现多源采集层，优先打通 AkShare 与公开网页源，并将 Copilot/web-access 深度检索作为每日自动任务的固定组成部分接入统一采集接口。

## 怎么做

1. 设计统一采集器接口。
2. 实现 AkShare 采集器。
3. 实现公开网页/RSS/公告页采集器。
4. 定义 Copilot/web-access 研究型采集器的输入输出协议。
5. 将采集结果统一落为标准化原始文档结构。

AkShare 接口开发前，优先查阅：
- 文档：`https://akshare.akfamily.xyz/`
- 仓库：`https://github.com/akfamily/akshare`

已确认：
- 自动化每日任务中，`web-access` 每次都要调用；
- 因此 research collector 不是纯人工工具，也不是可选增强项，而是主流程的固定可调度组成部分。

## 完成定义

- 至少两类来源可以稳定输出原始文档。
- 所有采集结果可统一入库或落盘。
- 后续分析层不直接依赖具体来源实现。

## 依赖

- `project-bootstrap`
