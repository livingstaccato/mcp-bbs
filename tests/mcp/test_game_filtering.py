"""Tests for MCP game filtering."""

from __future__ import annotations

import pytest

from bbsbot.mcp.server import _register_game_tools
from bbsbot.mcp.registry import get_manager
from fastmcp import FastMCP


@pytest.mark.asyncio
async def test_register_no_tools_without_prefixes() -> None:
    """Test that NO game tools are registered when no prefixes are provided.

    Game tools should only be registered when explicitly requested via --tools flag.
    """
    # Create a fresh app
    mcp = FastMCP("test-all")

    # Register with no prefixes (should register nothing)
    _register_game_tools(mcp, tool_prefixes=None)

    # Get the tools using get_tools()
    tools = await mcp.get_tools()

    # Should have NO tools (game tools only registered when prefixes provided)
    tool_names = [t.name for t in tools.values()]

    assert len(tool_names) == 0, "Should have NO game tools when no prefixes are provided"


@pytest.mark.asyncio
async def test_register_filtered_tools_tw2002() -> None:
    """Test that only tw2002 tools are registered when tool_prefixes='tw2002_'."""
    # Create a fresh app
    mcp = FastMCP("test-tw2002")

    # Register only tw2002 tools
    _register_game_tools(mcp, tool_prefixes="tw2002_")

    # Get the tools
    tools = await mcp.get_tools()
    tool_names = [t.name for t in tools.values()]

    # Check that we have tw2002 tools
    has_tw2002 = any(name.startswith("tw2002_") for name in tool_names)

    assert has_tw2002, "Should have tw2002_* tools when prefixes='tw2002_'"

    # No other game tools should be present
    for name in tool_names:
        # Should only have tw2002 tools
        assert name.startswith("tw2002_"), f"Only tw2002_* tools should be present but got {name}"


def test_registry_manager_has_tw2002() -> None:
    """Test that the registry manager has tw2002 registry."""
    manager = get_manager()

    # Should have tw2002 registry
    registries = manager.list_registries()
    assert "tw2002" in registries, f"tw2002 should be in registries: {registries}"

    # Get tw2002 registry and check for known tools
    tw2002_registry = manager.get_registry("tw2002")
    tw2002_tools = tw2002_registry.get_tools()

    # Should have some tools
    assert len(tw2002_tools) > 0, "tw2002 registry should have tools"

    # Check for expected tool names
    tool_names = list(tw2002_tools.keys())
    expected_tools = ["tw2002_get_bot_status", "tw2002_analyze_combat_readiness", "tw2002_debug"]
    for expected in expected_tools:
        assert expected in tool_names, f"Expected {expected} in tw2002 tools, got {tool_names}"
