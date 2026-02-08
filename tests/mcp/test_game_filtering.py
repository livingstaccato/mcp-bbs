"""Tests for MCP game filtering."""

from __future__ import annotations

import pytest

from bbsbot.mcp.server import _register_game_tools
from bbsbot.mcp.registry import get_manager
from fastmcp import FastMCP


@pytest.mark.asyncio
async def test_register_all_tools_no_filter() -> None:
    """Test that all game tools are registered when no filter is provided.

    Note: This tests only the game tools registration, not BBS tools.
    BBS tools are registered separately in the main app via @app.tool() decorators.
    """
    # Create a fresh app
    mcp = FastMCP("test-all")

    # Register all game tools (no filter)
    _register_game_tools(mcp, game_filter=None)

    # Get the tools using get_tools()
    tools = await mcp.get_tools()

    # Should have tools from multiple registries
    tool_names = [t.name for t in tools.values()]

    # Check that we have tw2002 tools (this is what _register_game_tools does)
    has_tw2002 = any(name.startswith("tw2002_") for name in tool_names)

    assert has_tw2002, "Should have tw2002_* tools when no filter is provided"

    # When no filter is provided, we should get all game tools, not just tw2002
    # For now, just verify we have game tools registered
    assert len(tool_names) > 0, "Should have some game tools registered"


@pytest.mark.asyncio
async def test_register_filtered_tools_tw2002() -> None:
    """Test that only tw2002 tools are registered when game_filter='tw2002'.

    Note: BBS tools are not filtered (always included per design decision).
    """
    # Create a fresh app
    mcp = FastMCP("test-tw2002")

    # Register only tw2002 tools (BBS tools are still included, not filtered)
    _register_game_tools(mcp, game_filter="tw2002")

    # Get the tools
    tools = await mcp.get_tools()
    tool_names = [t.name for t in tools.values()]

    # Check that we have tw2002 tools (BBS tools won't be in this app
    # since this is just the game tools registration)
    has_tw2002 = any(name.startswith("tw2002_") for name in tool_names)

    assert has_tw2002, "Should have tw2002_* tools when filtered to tw2002"

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
