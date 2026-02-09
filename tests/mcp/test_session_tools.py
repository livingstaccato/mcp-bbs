"""Tests for TW2002 session-level MCP tools (connect/login)."""

from __future__ import annotations

import inspect

import pytest

from bbsbot.mcp.registry import get_manager


def test_tw2002_session_tools_exist() -> None:
    # Import to trigger registration
    from bbsbot.games.tw2002 import mcp_tools  # noqa: F401

    manager = get_manager()
    registry = manager.get_registry("tw2002")
    assert registry is not None

    tools = registry.get_tools()
    assert "tw2002_connect" in tools
    assert "tw2002_login" in tools


@pytest.mark.asyncio
async def test_tw2002_login_requires_connection() -> None:
    # Import to trigger registration
    from bbsbot.games.tw2002 import mcp_tools  # noqa: F401

    manager = get_manager()
    registry = manager.get_registry("tw2002")
    assert registry is not None

    tools = registry.get_tools()
    login_func = tools["tw2002_login"]

    assert inspect.iscoroutinefunction(login_func)

    # Without an MCP session connected, login should return a structured error.
    result = await login_func(username="test", character_password="pw")
    assert result["success"] is False
    assert "Not connected" in (result.get("error") or "")

