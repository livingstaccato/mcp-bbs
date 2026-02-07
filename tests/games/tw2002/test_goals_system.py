"""Tests for TW2002 goals system + MCP tool registration."""

from __future__ import annotations

import asyncio
from pathlib import Path


def test_goals_config_loads_defaults() -> None:
    from bbsbot.games.tw2002.config import BotConfig

    config = BotConfig()
    goals_config = config.trading.ai_strategy.goals
    goal_ids = [g.id for g in goals_config.available]

    assert "profit" in goal_ids
    assert "combat" in goal_ids
    assert "exploration" in goal_ids
    assert "banking" in goal_ids


def test_goal_selection_low_credits_prefers_profit() -> None:
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy

    config = BotConfig()
    knowledge = SectorKnowledge(
        knowledge_dir=Path("/tmp/test_knowledge"),
        character_name="test",
    )
    strategy = AIStrategy(config, knowledge)

    state = GameState(
        context="sector_command",
        sector=1,
        credits=5000,
        turns_left=100,
    )

    goal = asyncio.run(strategy._select_goal(state))
    assert goal == "profit"


def test_goal_injected_into_prompt_builder() -> None:
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
    from bbsbot.games.tw2002.strategies.ai.prompts import PromptBuilder

    builder = PromptBuilder()
    state = GameState(context="sector_command", sector=1)
    knowledge = SectorKnowledge(
        knowledge_dir=Path("/tmp/test_knowledge"),
        character_name="test",
    )

    messages = builder.build(
        state,
        knowledge,
        stats={},
        goal_description="Test goal",
        goal_instructions="Do test things",
    )

    assert "Test goal" in messages[0].content
    assert "Do test things" in messages[0].content


def test_mcp_registry_registers_tools() -> None:
    from bbsbot.mcp.registry import create_registry

    registry = create_registry("test")

    @registry.tool()
    async def test_tool(arg: str) -> dict:
        return {"result": arg}

    tools = registry.get_tools()
    assert "test_test_tool" in tools


def test_tw2002_tools_registered() -> None:
    # Import triggers registration
    from bbsbot.games.tw2002 import mcp_tools  # noqa: F401
    from bbsbot.mcp.registry import get_manager

    tools = get_manager().get_all_tools()

    expected = {
        "tw2002_set_goal",
        "tw2002_get_goals",
        "tw2002_get_trade_opportunities",
        "tw2002_analyze_combat_readiness",
        "tw2002_get_bot_status",
        "tw2002_get_goal_phases",
        "tw2002_get_goal_visualization",
    }

    missing = expected - set(tools)
    assert not missing, f"Missing tools: {sorted(missing)}"

