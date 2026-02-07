"""Tests for MCP "spy" goal visualization tools."""

from __future__ import annotations

import asyncio

from bbsbot.games.tw2002.config import BotConfig, GoalPhase


def test_mcp_get_goal_visualization(monkeypatch):
    """Tool returns rendered strings when phases exist."""
    from bbsbot.games.tw2002 import mcp_tools

    class FakeStrategy:
        name = "ai_strategy"

        def __init__(self) -> None:
            self._current_turn = 30
            self._max_turns = 100
            self._goal_phases = [
                GoalPhase(
                    goal_id="profit",
                    start_turn=1,
                    end_turn=20,
                    status="completed",
                    trigger_type="auto",
                    metrics={"start_credits": 10000, "end_credits": 25000},
                    reason="Start",
                ),
                GoalPhase(
                    goal_id="combat",
                    start_turn=21,
                    end_turn=None,
                    status="active",
                    trigger_type="auto",
                    metrics={"start_credits": 25000, "end_credits": 30000},
                    reason="Auto",
                ),
            ]
            self._current_phase = self._goal_phases[-1]

    class FakeBot:
        def __init__(self) -> None:
            self.character_name = "test"
            self.config = BotConfig()
            self.strategy = FakeStrategy()

    class FakeSessionManager:
        def __init__(self, bot) -> None:
            self._sessions = ["sid"]
            self._bot = bot

        def get_bot(self, session_id: str):
            assert session_id == "sid"
            return self._bot

    import bbsbot.mcp.server as mcp_server

    bot = FakeBot()
    monkeypatch.setattr(mcp_server, "session_manager", FakeSessionManager(bot))

    result = asyncio.run(mcp_tools.get_goal_visualization())
    assert result["success"] is True
    assert "COMBAT" in (result["compact"] or "")
    assert "Legend:" in (result["timeline"] or "")
    assert "GOAL SESSION SUMMARY" in (result["summary"] or "")
    assert result["current_turn"] == 30


def test_mcp_get_goal_phases(monkeypatch):
    """Tool returns raw phase data."""
    from bbsbot.games.tw2002 import mcp_tools

    class FakeStrategy:
        def __init__(self) -> None:
            self._current_turn = 5
            self._goal_phases = [
                GoalPhase(
                    goal_id="profit",
                    start_turn=1,
                    end_turn=None,
                    status="active",
                    trigger_type="auto",
                    metrics={},
                    reason="Start",
                ),
            ]

    class FakeBot:
        def __init__(self) -> None:
            self.strategy = FakeStrategy()

    class FakeSessionManager:
        def __init__(self, bot) -> None:
            self._sessions = ["sid"]
            self._bot = bot

        def get_bot(self, session_id: str):
            return self._bot

    import bbsbot.mcp.server as mcp_server

    monkeypatch.setattr(mcp_server, "session_manager", FakeSessionManager(FakeBot()))

    result = asyncio.run(mcp_tools.get_goal_phases())
    assert result["success"] is True
    assert result["current_turn"] == 5
    assert result["phases"][0]["goal_id"] == "profit"

