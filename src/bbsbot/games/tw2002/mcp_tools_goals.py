# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TW2002 goal management MCP tools.

Provides goal-related functionality accessible via MCP interface.
"""

from __future__ import annotations

from typing import Any

from bbsbot.games.tw2002.mcp_context import resolve_active_bot
from bbsbot.games.tw2002.mcp_tools import registry
from bbsbot.logging import get_logger

logger = get_logger(__name__)


def _get_active_bot():
    bot, _, _ = resolve_active_bot()
    return bot


@registry.tool()
async def set_goal(goal: str, duration_turns: int = 0) -> dict[str, Any]:
    """Set current bot goal (profit/combat/exploration/banking).

    Changes the bot's strategic objective, affecting decision-making prompts
    and behavior. Goals influence what trades to pursue, whether to seek
    or avoid combat, and resource allocation priorities.

    Args:
        goal: Goal ID to activate ('profit', 'combat', 'exploration', 'banking')
        duration_turns: How many turns to maintain goal (0 = until manually changed)

    Returns:
        Status and goal details

    Example:
        await tw2002_set_goal(goal="combat", duration_turns=50)
        # Bot focuses on combat for next 50 turns
    """
    # Get active bot
    bot = _get_active_bot()

    if not bot:
        return {
            "success": False,
            "error": "No active bot found",
        }

    # Check if bot has AI strategy
    if not hasattr(bot, "strategy") or not bot.strategy:
        return {
            "success": False,
            "error": "Bot has no strategy",
        }

    strategy = bot.strategy
    if not hasattr(strategy, "set_goal"):
        return {
            "success": False,
            "error": f"Strategy '{type(strategy).__name__}' does not support goals",
        }

    # Set the goal
    strategy.set_goal(goal, duration_turns)

    # Get goal config
    goal_config = strategy._get_goal_config(goal)

    return {
        "success": True,
        "goal": goal,
        "duration_turns": duration_turns,
        "description": goal_config.description if goal_config else None,
        "instructions": goal_config.instructions if goal_config else None,
    }


@registry.tool()
async def get_goals() -> dict[str, Any]:
    """Get available goals and their trigger conditions.

    Returns all configured goals with their descriptions, priorities,
    and the conditions that automatically trigger each goal.

    Returns:
        Available goals and current goal status

    Example:
        goals = await tw2002_get_goals()
        # Returns: {current: "profit", available: [...], ...}
    """
    # Get active bot
    bot = _get_active_bot()

    if not bot:
        return {
            "success": False,
            "error": "No active bot found",
        }

    # Check if bot has AI strategy
    if not hasattr(bot, "strategy") or not bot.strategy:
        return {
            "success": False,
            "error": "Bot has no strategy",
        }

    strategy = bot.strategy
    if not hasattr(strategy, "_settings") or not hasattr(strategy._settings, "goals"):
        return {
            "success": False,
            "error": "Strategy does not support goals",
        }

    goals_config = strategy._settings.goals

    # Format goals
    available_goals = []
    for goal in goals_config.available:
        available_goals.append(
            {
                "id": goal.id,
                "priority": goal.priority,
                "description": goal.description,
                "instructions": goal.instructions,
                "triggers": {
                    "credits_below": goal.trigger_when.credits_below,
                    "credits_above": goal.trigger_when.credits_above,
                    "fighters_below": goal.trigger_when.fighters_below,
                    "fighters_above": goal.trigger_when.fighters_above,
                    "shields_below": goal.trigger_when.shields_below,
                    "shields_above": goal.trigger_when.shields_above,
                    "turns_remaining_above": goal.trigger_when.turns_remaining_above,
                    "turns_remaining_below": goal.trigger_when.turns_remaining_below,
                    "sectors_known_below": goal.trigger_when.sectors_known_below,
                    "in_fedspace": goal.trigger_when.in_fedspace,
                },
            }
        )

    return {
        "success": True,
        "current_goal": strategy.get_current_goal(),
        "available": available_goals,
        "reevaluate_every_turns": goals_config.reevaluate_every_turns,
        "mode": goals_config.current,  # "auto" or specific goal ID
    }


@registry.tool()
async def get_goal_phases() -> dict[str, Any]:
    """Return raw goal phase data (if the active strategy supports it)."""
    bot = _get_active_bot()
    if not bot or not getattr(bot, "strategy", None):
        return {"success": False, "error": "No active bot found"}

    strategy = bot.strategy
    phases = getattr(strategy, "_goal_phases", None)
    if not phases:
        return {
            "success": True,
            "phases": [],
            "current_turn": getattr(strategy, "_current_turn", 0),
        }

    return {
        "success": True,
        "phases": [p.model_dump(mode="json") for p in phases],
        "current_turn": getattr(strategy, "_current_turn", 0),
    }


@registry.tool()
async def get_goal_visualization(max_turns: int | None = None) -> dict[str, Any]:
    """Return rendered goal visualization strings (compact/timeline/summary).

    This is intended as a "spy" interface to retrieve the visualization output
    while a bot is running in this process.
    """
    bot = _get_active_bot()
    if not bot or not getattr(bot, "strategy", None):
        return {"success": False, "error": "No active bot found"}

    strategy = bot.strategy
    phases = getattr(strategy, "_goal_phases", None) or []
    phase = getattr(strategy, "_current_phase", None)
    current_turn = getattr(strategy, "_current_turn", 0)

    resolved_max_turns = max_turns or getattr(strategy, "_max_turns", None)
    if not resolved_max_turns:
        cfg = getattr(bot, "config", None)
        resolved_max_turns = getattr(getattr(cfg, "session", None), "max_turns_per_session", None) or 1
    if resolved_max_turns <= 0:
        resolved_max_turns = 1

    compact = None
    timeline = None
    summary = None

    if phase is not None:
        from bbsbot.games.tw2002.visualization import GoalStatusDisplay

        compact = GoalStatusDisplay().render_compact(
            phase=phase,
            current_turn=current_turn,
            max_turns=resolved_max_turns,
        )

    if phases:
        from bbsbot.games.tw2002.visualization import GoalSummaryReport, GoalTimeline

        timeline_obj = GoalTimeline(phases, current_turn=current_turn, max_turns=resolved_max_turns)
        timeline = "\n".join([timeline_obj.render_progress_bar(), timeline_obj.render_legend()])

        summary = GoalSummaryReport(phases, max_turns=resolved_max_turns).render_full_summary()

    return {
        "success": True,
        "compact": compact,
        "timeline": timeline,
        "summary": summary,
        "phases": [p.model_dump(mode="json") for p in phases],
        "current_turn": current_turn,
        "max_turns": resolved_max_turns,
        "character_name": getattr(bot, "character_name", "unknown"),
        "strategy": getattr(strategy, "name", type(strategy).__name__),
    }
