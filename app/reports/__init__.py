"""
日报输出模块（Report Output）。

将 A 股映射结果输出到日报，支持 Markdown 和 JSON 两种格式。

主要组件：
- DailyReport：完整日报数据结构
- DailyReportBuilder：日报构建器
- MarkdownReportGenerator：Markdown 格式生成器
- JsonReportGenerator：JSON 格式生成器
- ReportArchiveManager：报告归档管理器
"""

from app.reports.core import (
    DailyReport,
    DailyReportHeader,
    DailyReportChainEntry,
    RiskWarning,
    DailyReportBuilder,
    MarkdownReportGenerator,
    JsonReportGenerator,
    ReportArchiveManager,
    create_report_builder,
    create_archive_manager,
    generate_markdown_report,
    generate_json_report,
)

__all__ = [
    "DailyReport",
    "DailyReportHeader",
    "DailyReportChainEntry",
    "RiskWarning",
    "DailyReportBuilder",
    "MarkdownReportGenerator",
    "JsonReportGenerator",
    "ReportArchiveManager",
    "create_report_builder",
    "create_archive_manager",
    "generate_markdown_report",
    "generate_json_report",
]
