# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for TW2002 MCP capability/discovery tools."""

from __future__ import annotations

import asyncio


def test_mcp_capabilities_tool_shape() -> None:
    from bbsbot.games.tw2002 import mcp_tools

    result = asyncio.run(mcp_tools.capabilities())
    assert result["success"] is True
    assert "entrypoints" in result
    assert "tool_groups" in result
    assert "tw2002_bootstrap" in result["entrypoints"]["quick_start"]


def test_set_directive_sets_and_clears_strategy_directive(monkeypatch) -> None:
    from bbsbot.games.tw2002 import mcp_tools

    class FakeStrategy:
        name = "ai_strategy"
        _current_turn = 17

    class FakeBot:
        strategy = FakeStrategy()

    monkeypatch.setattr(mcp_tools, "_get_active_bot", lambda: (FakeBot(), "session_1", None))

    set_result = asyncio.run(mcp_tools.set_directive("Trade safely near fedspace", turns=6))
    assert set_result["success"] is True
    assert set_result["active_until_turn"] == 23

    clear_result = asyncio.run(mcp_tools.set_directive("", turns=0))
    assert clear_result["success"] is True
    assert clear_result["directive"] is None
