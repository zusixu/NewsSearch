"""
app/analysis/react/tools.py — ReAct tool definitions and registry.

Defines the Tool frozen-dataclass, a ToolRegistry for managing named tools,
and three built-in tools: web_search, web_fetch, akshare_query.

Design decisions
----------------
- Tool is a frozen dataclass with an ``execute`` callable; it is safe to share
  across sessions.
- ToolRegistry is a plain dict-based registry — not a service locator.
- web_search is a stub in the default implementation; Claude Code environments
  may later delegate to the ``web-access`` skill.
- web_fetch uses ``requests`` for HTTP GET and returns a truncated text summary.
- akshare_query is a stub; the real ``akshare`` integration is deferred.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Tool — frozen dataclass representing a callable tool
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    """
    A named, described, parameterised tool that the ReAct agent may invoke.

    Fields
    ------
    name
        Unique tool identifier, e.g. ``"web_search"``.
    description
        Human-readable description surfaced to the LLM for tool selection.
    parameters
        JSON Schema dictionary describing the tool's input parameters.
    execute
        Callable that receives the parameter dict and returns a string
        observation. Must be picklable if sessions need serialisation
        (avoid closures/lambdas).
    """

    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., str] = field(compare=False, hash=False)


# ---------------------------------------------------------------------------
# ToolRegistry — manages tool registration / lookup / execution
# ---------------------------------------------------------------------------


class ToolRegistry:
    """
    Registry of named :class:`Tool` instances.

    Provides ``register``, ``get``, ``list_tools``, ``execute``, and
    ``to_schema_dicts`` (for inclusion in LLM prompts).
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # -- registration --------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """Register a tool (overwrites any existing tool with the same name)."""
        if not tool.name:
            raise ValueError("Tool name must not be empty.")
        self._tools[tool.name] = tool

    # -- lookup --------------------------------------------------------------

    def get(self, name: str) -> Tool | None:
        """Return the :class:`Tool` registered under *name*, or ``None``."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """Return all registered tools as a list."""
        return list(self._tools.values())

    def to_schema_dicts(self) -> list[dict[str, Any]]:
        """
        Return a list of ``{"name": ..., "description": ..., "parameters": ...}``
        dicts suitable for inclusion in an LLM system or user prompt.
        """
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    # -- execution -----------------------------------------------------------

    def execute(self, name: str, params: dict[str, Any] | None = None) -> str:
        """
        Execute the named tool with *params* and return the observation string.

        Raises ``ValueError`` when the tool name is unknown.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name!r}")
        return tool.execute(**(params or {}))


# ---------------------------------------------------------------------------
# Built-in tool implementations
# ---------------------------------------------------------------------------


def _web_search_stub(query: str, **kwargs: Any) -> str:
    """Stub implementation for web_search; delegates to web-access skill
    when running inside Claude Code, otherwise returns a placeholder."""
    # Detect Claude Code environment marker
    if os.environ.get("CLAUDE_CODE_AVAILABLE"):
        return (
            f"web_search tool: use web-access skill to search for: {query}\n"
            f"(additional params: {json.dumps(kwargs, ensure_ascii=False) if kwargs else 'none'})"
        )
    return f"web_search tool called with query: {query}"


def _web_fetch_impl(url: str, **kwargs: Any) -> str:
    """Fetch the content of *url* via HTTP GET and return a text summary
    (first 2000 characters)."""
    try:
        import requests  # type: ignore[import-untyped]
    except ImportError:
        return f"web_fetch error: requests library not available; cannot fetch {url}"

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "mm-pipeline/0.1"})
        resp.raise_for_status()
        text = resp.text[:2000]
        return f"web_fetch result for {url} (HTTP {resp.status_code}):\n{text}"
    except requests.RequestException as exc:
        return f"web_fetch error fetching {url}: {exc}"
    except Exception as exc:
        return f"web_fetch unexpected error for {url}: {exc}"


def _akshare_query_stub(**params: Any) -> str:
    """Stub for akshare-based A-share data queries.  Real akshare integration
    is deferred to a future phase."""
    query_str = json.dumps(params, ensure_ascii=False)
    return f"akshare tool: query {query_str}"


# ---------------------------------------------------------------------------
# Pre-built tool instances
# ---------------------------------------------------------------------------

web_search_tool = Tool(
    name="web_search",
    description="Search the web for investment-related information. Returns text snippets.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string.",
            },
        },
        "required": ["query"],
    },
    execute=_web_search_stub,
)

web_fetch_tool = Tool(
    name="web_fetch",
    description="Fetch and extract text content from a URL. Returns the first 2000 characters.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to fetch content from.",
            },
        },
        "required": ["url"],
    },
    execute=_web_fetch_impl,
)

akshare_query_tool = Tool(
    name="akshare_query",
    description="Query A-share market data (price, fundamentals, etc.) by stock code or keyword.",
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Stock code (e.g. '000001', '600519').",
            },
        },
        "required": ["code"],
    },
    execute=_akshare_query_stub,
)


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

tool_registry = ToolRegistry()
tool_registry.register(web_search_tool)
tool_registry.register(web_fetch_tool)
tool_registry.register(akshare_query_tool)
