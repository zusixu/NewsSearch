"""app.analysis.react — ReAct multi-step analysis engine."""

from app.analysis.react.tools import (
    Tool,
    ToolRegistry,
    tool_registry,
    web_search_tool,
    web_fetch_tool,
    akshare_query_tool,
)
from app.analysis.react.session import (
    ReActSession,
    ReActStep,
)
from app.analysis.react.prompts import (
    GrouperContext,
    ReActContext,
    build_grouper_prompt_context,
    build_react_step_prompt_context,
    build_react_finalize_prompt_context,
)
from app.analysis.react.engine import (
    ReActAnalysisEngine,
    ReActEngineConfig,
)

__all__ = [
    # tools
    "Tool",
    "ToolRegistry",
    "tool_registry",
    "web_search_tool",
    "web_fetch_tool",
    "akshare_query_tool",
    # session
    "ReActStep",
    "ReActSession",
    # prompts
    "GrouperContext",
    "ReActContext",
    "build_grouper_prompt_context",
    "build_react_step_prompt_context",
    "build_react_finalize_prompt_context",
    # engine
    "ReActAnalysisEngine",
    "ReActEngineConfig",
]
