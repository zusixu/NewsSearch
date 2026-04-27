"""
tests/test_react_tools.py

Tests for ReAct tool definitions, ToolRegistry, and built-in tool implementations.

Coverage:
- Tool dataclass creation and fields
- ToolRegistry.register / get / list_tools
- ToolRegistry.execute success and failure (unknown tool)
- ToolRegistry.to_schema_dicts format
- web_search_tool stub output
- web_fetch_tool (mock requests)
- akshare_query_tool stub output
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.analysis.react.tools import (
    Tool,
    ToolRegistry,
    web_search_tool,
    web_fetch_tool,
    akshare_query_tool,
    tool_registry,
)


# ---------------------------------------------------------------------------
# Tool dataclass tests
# ---------------------------------------------------------------------------


class TestToolDataclass:
    """Tests for the Tool frozen dataclass."""

    def test_create_tool_with_minimal_fields(self) -> None:
        """A Tool can be created with name, description, parameters, and execute."""
        t = Tool(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            execute=lambda **kw: "done",
        )
        assert t.name == "test_tool"
        assert t.description == "A test tool"
        assert t.parameters == {"type": "object", "properties": {}}

    def test_tool_is_frozen(self) -> None:
        """Tool is a frozen dataclass — cannot be mutated."""
        t = Tool(
            name="test_tool",
            description="desc",
            parameters={},
            execute=lambda **kw: "result",
        )
        with pytest.raises(Exception):
            t.name = "other"  # type: ignore[misc]

    def test_tool_execute_callable(self) -> None:
        """Tool.execute is the stored callable."""
        def my_exec(**kw: object) -> str:
            return f"called with {kw}"
        t = Tool(name="t", description="d", parameters={}, execute=my_exec)
        assert t.execute(foo="bar") == "called with {'foo': 'bar'}"

    def test_tool_equality_excludes_execute(self) -> None:
        """Two Tools with same name/desc/params but different execute
        compare equal because execute is excluded from comparison."""
        t1 = Tool(name="t", description="d", parameters={}, execute=lambda **kw: "a")
        t2 = Tool(name="t", description="d", parameters={}, execute=lambda **kw: "b")
        assert t1 == t2

    def test_tool_equality_different_names(self) -> None:
        """Tools with different names are not equal."""
        t1 = Tool(name="a", description="d", parameters={}, execute=lambda **kw: "x")
        t2 = Tool(name="b", description="d", parameters={}, execute=lambda **kw: "x")
        assert t1 != t2

    def test_tool_not_hashable_due_to_dict_params(self) -> None:
        """Tool is not hashable because 'parameters' is a plain dict.
        This is by design — frozen dataclasses with mutable-typed fields
        (dict, list) cannot compute a stable hash."""
        t1 = Tool(name="t", description="d", parameters={}, execute=lambda **kw: "x")
        with pytest.raises(TypeError):
            hash(t1)


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------


class TestToolRegistry:
    """Tests for ToolRegistry."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        """Fresh empty registry."""
        return ToolRegistry()

    @pytest.fixture
    def sample_tool(self) -> Tool:
        """A sample tool for registration."""
        return Tool(
            name="echo",
            description="Echo back the message",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Text to echo."},
                },
                "required": ["message"],
            },
            execute=lambda **kw: f"echo: {kw.get('message', '')}",
        )

    # -- register ------------------------------------------------------------

    def test_register_adds_tool(self, registry, sample_tool) -> None:
        """register() adds a tool to the registry."""
        registry.register(sample_tool)
        assert registry.get("echo") is sample_tool

    def test_register_overwrites_same_name(self, registry) -> None:
        """register() overwrites an existing tool with the same name."""
        t1 = Tool(name="x", description="first", parameters={}, execute=lambda **kw: "a")
        t2 = Tool(name="x", description="second", parameters={}, execute=lambda **kw: "b")
        registry.register(t1)
        registry.register(t2)
        assert registry.get("x") is t2

    def test_register_empty_name_raises(self, registry) -> None:
        """register() raises ValueError on empty tool name."""
        t = Tool(name="", description="d", parameters={}, execute=lambda **kw: "x")
        with pytest.raises(ValueError, match="Tool name must not be empty"):
            registry.register(t)

    # -- get ----------------------------------------------------------------

    def test_get_known_tool(self, registry, sample_tool) -> None:
        """get() returns the tool for a registered name."""
        registry.register(sample_tool)
        assert registry.get("echo") is sample_tool

    def test_get_unknown_tool_returns_none(self, registry) -> None:
        """get() returns None for unknown names."""
        assert registry.get("nonexistent") is None

    # -- list_tools ----------------------------------------------------------

    def test_list_tools_empty(self, registry) -> None:
        """list_tools() returns empty list for empty registry."""
        assert registry.list_tools() == []

    def test_list_tools_returns_all(self, registry, sample_tool) -> None:
        """list_tools() returns all registered tools."""
        t2 = Tool(name="t2", description="d2", parameters={}, execute=lambda **kw: "x")
        registry.register(sample_tool)
        registry.register(t2)
        tools = registry.list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"echo", "t2"}

    # -- execute ------------------------------------------------------------

    def test_execute_calls_tool(self, registry, sample_tool) -> None:
        """execute() calls the tool and returns its result."""
        registry.register(sample_tool)
        result = registry.execute("echo", {"message": "hello"})
        assert result == "echo: hello"

    def test_execute_no_params(self, registry) -> None:
        """execute() with no params passes empty dict to the tool."""
        t = Tool(
            name="noop", description="d", parameters={},
            execute=lambda **kw: f"called with {len(kw)} params",
        )
        registry.register(t)
        result = registry.execute("noop")
        assert result == "called with 0 params"

    def test_execute_unknown_tool_raises(self, registry) -> None:
        """execute() raises ValueError for unknown tool names."""
        with pytest.raises(ValueError, match="Unknown tool"):
            registry.execute("nonexistent")

    # -- to_schema_dicts -----------------------------------------------------

    def test_to_schema_dicts_empty(self, registry) -> None:
        """to_schema_dicts() returns empty list for empty registry."""
        assert registry.to_schema_dicts() == []

    def test_to_schema_dicts_format(self, registry, sample_tool) -> None:
        """to_schema_dicts() returns properly formatted dicts."""
        registry.register(sample_tool)
        schemas = registry.to_schema_dicts()
        assert len(schemas) == 1
        s = schemas[0]
        assert s["name"] == "echo"
        assert s["description"] == "Echo back the message"
        assert s["parameters"] == sample_tool.parameters
        assert "execute" not in s  # execute should never appear in schema


# ---------------------------------------------------------------------------
# Built-in tools tests
# ---------------------------------------------------------------------------


class TestWebSearchTool:
    """Tests for the web_search built-in tool."""

    def test_tool_has_correct_name(self) -> None:
        """web_search_tool has name 'web_search'."""
        assert web_search_tool.name == "web_search"

    def test_tool_has_description(self) -> None:
        """web_search_tool has a non-empty description."""
        assert len(web_search_tool.description) > 0

    def test_tool_parameters_require_query(self) -> None:
        """web_search_tool parameters schema requires 'query'."""
        assert "query" in web_search_tool.parameters["required"]

    def test_execute_returns_non_empty_string(self) -> None:
        """web_search_tool execution returns a non-empty string."""
        result = web_search_tool.execute(query="AI investment news")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_contains_query(self) -> None:
        """web_search_tool output contains the search query."""
        result = web_search_tool.execute(query="test query")
        assert "test query" in result

    def test_execute_handles_extra_kwargs(self) -> None:
        """web_search_tool execution accepts extra kwargs without error."""
        result = web_search_tool.execute(query="q", lang="en", limit=10)
        assert isinstance(result, str)


class TestWebFetchTool:
    """Tests for the web_fetch built-in tool."""

    def test_tool_has_correct_name(self) -> None:
        """web_fetch_tool has name 'web_fetch'."""
        assert web_fetch_tool.name == "web_fetch"

    def test_tool_has_description(self) -> None:
        """web_fetch_tool has a non-empty description."""
        assert len(web_fetch_tool.description) > 0

    def test_tool_parameters_require_url(self) -> None:
        """web_fetch_tool parameters schema requires 'url'."""
        assert "url" in web_fetch_tool.parameters["required"]

    def test_execute_returns_error_when_requests_not_available(self) -> None:
        """web_fetch_tool returns an error message when requests is absent."""
        with patch.dict("sys.modules", {"requests": None}):
            # The import happens inside the function — we need to simulate
            # an ImportError.  Use a side_effect on __import__.
            import builtins
            orig_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "requests":
                    raise ImportError("no requests")
                return orig_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=mock_import):
                result = web_fetch_tool.execute(url="https://example.com")
                assert "error" in result.lower()
                assert "not available" in result

    def test_execute_still_returns_string_on_error(self) -> None:
        """web_fetch_tool always returns a string (never raises)."""
        # This test does NOT mock requests — but since it calls a real URL,
        # it may succeed or fail depending on network.  Either way it must
        # not raise and must return a string.
        result = web_fetch_tool.execute(url="https://invalid.example.invalid")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_with_extra_kwargs(self) -> None:
        """web_fetch_tool accepts extra kwargs."""
        result = web_fetch_tool.execute(url="https://nope.test", timeout=5)
        assert isinstance(result, str)


class TestAkShareQueryTool:
    """Tests for the akshare_query built-in tool."""

    def test_tool_has_correct_name(self) -> None:
        """akshare_query_tool has name 'akshare_query'."""
        assert akshare_query_tool.name == "akshare_query"

    def test_tool_has_description(self) -> None:
        """akshare_query_tool has a non-empty description."""
        assert len(akshare_query_tool.description) > 0

    def test_tool_parameters_require_code(self) -> None:
        """akshare_query_tool parameters schema requires 'code'."""
        assert "code" in akshare_query_tool.parameters["required"]

    def test_execute_returns_stub_output(self) -> None:
        """akshare_query_tool returns stub output containing the query params."""
        result = akshare_query_tool.execute(code="600519")
        assert isinstance(result, str)
        assert "akshare tool" in result
        assert "600519" in result

    def test_execute_with_extra_params(self) -> None:
        """akshare_query_tool accepts extra kwargs."""
        result = akshare_query_tool.execute(code="000001", period="daily")
        assert isinstance(result, str)
        assert "000001" in result


# ---------------------------------------------------------------------------
# Default registry tests
# ---------------------------------------------------------------------------


class TestDefaultToolRegistry:
    """Tests for the module-level tool_registry."""

    def test_default_registry_has_all_three_tools(self) -> None:
        """The default tool_registry contains web_search, web_fetch, akshare_query."""
        tools = tool_registry.list_tools()
        names = {t.name for t in tools}
        assert names == {"web_search", "web_fetch", "akshare_query"}

    def test_default_registry_execute_web_search(self) -> None:
        """Default registry can execute web_search."""
        result = tool_registry.execute("web_search", {"query": "test"})
        assert "test" in result

    def test_default_registry_execute_akshare_query(self) -> None:
        """Default registry can execute akshare_query."""
        result = tool_registry.execute("akshare_query", {"code": "600519"})
        assert "600519" in result

    def test_default_registry_to_schema_dicts(self) -> None:
        """Default registry produces 3 schema dicts."""
        schemas = tool_registry.to_schema_dicts()
        assert len(schemas) == 3
        for s in schemas:
            assert "name" in s
            assert "description" in s
            assert "parameters" in s
            assert "execute" not in s
