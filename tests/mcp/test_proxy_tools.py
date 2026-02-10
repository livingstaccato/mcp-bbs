"""Tests for MCP proxy tools."""

from __future__ import annotations

import pytest

from bbsbot.mcp.registry import get_manager


def test_debug_proxy_tool_exists() -> None:
    """Test that the tw2002_debug proxy tool is registered."""
    # Import to trigger registration

    manager = get_manager()
    tw2002_registry = manager.get_registry("tw2002")

    assert tw2002_registry is not None, "tw2002_registry should exist"

    tw2002_tools = tw2002_registry.get_tools()
    tool_names = list(tw2002_tools.keys())

    # Check for debug tool
    debug_tool_name = "tw2002_debug"
    assert debug_tool_name in tool_names, f"Debug proxy tool should exist. Available: {tool_names}"


@pytest.mark.asyncio
async def test_debug_proxy_tool_structure() -> None:
    """Test that the debug proxy tool has the expected structure."""
    # Import to trigger registration

    manager = get_manager()
    tw2002_registry = manager.get_registry("tw2002")
    tw2002_tools = tw2002_registry.get_tools()

    debug_func = tw2002_tools["tw2002_debug"]

    # Should be an async function
    import inspect

    assert inspect.iscoroutinefunction(debug_func), "debug tool should be async"

    # Should have docstring
    assert debug_func.__doc__ is not None, "debug tool should have docstring"
    assert "Debug proxy" in debug_func.__doc__, "docstring should mention proxy"


def test_debug_proxy_tool_commands() -> None:
    """Test that debug proxy tool documents expected commands."""

    manager = get_manager()
    tw2002_registry = manager.get_registry("tw2002")
    tw2002_tools = tw2002_registry.get_tools()

    debug_func = tw2002_tools["tw2002_debug"]

    # Check docstring for expected commands
    docstring = debug_func.__doc__ or ""
    expected_commands = [
        "bot_state",
        "learning_state",
        "llm_stats",
        "session_events",
    ]

    for cmd in expected_commands:
        assert cmd in docstring, f"Docstring should document '{cmd}' command"
