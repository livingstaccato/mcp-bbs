"""TW2002-specific MCP tools.

Provides game-specific functionality accessible via MCP interface.
Tools are prefixed with 'tw2002_' to distinguish from core bbs_ tools.
"""

from __future__ import annotations

import logging
from typing import Any

from bbsbot.mcp.registry import create_registry

logger = logging.getLogger(__name__)

# Create TW2002 tool registry
registry = create_registry("tw2002")


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
    from bbsbot.mcp.server import session_manager

    # Get active bot
    bot = None
    for session_id in session_manager._sessions:
        bot = session_manager.get_bot(session_id)
        if bot:
            break

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
    from bbsbot.mcp.server import session_manager

    # Get active bot
    bot = None
    for session_id in session_manager._sessions:
        bot = session_manager.get_bot(session_id)
        if bot:
            break

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
        available_goals.append({
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
        })

    return {
        "success": True,
        "current_goal": strategy.get_current_goal(),
        "available": available_goals,
        "reevaluate_every_turns": goals_config.reevaluate_every_turns,
        "mode": goals_config.current,  # "auto" or specific goal ID
    }


@registry.tool()
async def set_directive(directive: str, turns: int = 0) -> dict[str, Any]:
    """Set natural language directive for AI strategy.

    Allows you to give the bot free-form instructions that will be
    injected into decision-making prompts. Useful for quick behavior
    adjustments without changing goals.

    Args:
        directive: Natural language instruction (e.g., "Focus on combat and avoid trading")
        turns: How many turns to follow directive (0 = until cleared)

    Returns:
        Confirmation and how directive affects behavior

    Example:
        await tw2002_set_directive(
            "I need you to build up fighters. Avoid unprofitable trades.",
            turns=30
        )
    """
    from bbsbot.mcp.server import session_manager

    # Get active bot
    bot = None
    for session_id in session_manager._sessions:
        bot = session_manager.get_bot(session_id)
        if bot:
            break

    if not bot:
        return {
            "success": False,
            "error": "No active bot found",
        }

    # For now, we'll implement this as a special goal
    # In the future, this could be a separate directive system
    return {
        "success": False,
        "error": "Custom directives not yet implemented - use set_goal for now",
        "suggestion": "Use tw2002_set_goal() to change bot behavior",
    }


@registry.tool()
async def get_trade_opportunities(
    max_hops: int = 3,
    min_profit: int = 1000,
) -> list[dict[str, Any]]:
    """Analyze current trade opportunities.

    Finds profitable trade routes from the bot's current location
    based on known port data and sector connections.

    Args:
        max_hops: Maximum warp distance to consider (default 3)
        min_profit: Minimum profit threshold (default 1000)

    Returns:
        List of trade opportunities with profit estimates

    Example:
        opps = await tw2002_get_trade_opportunities(max_hops=5, min_profit=2000)
        # Returns: [{buy_sector: 100, sell_sector: 150, profit: 3500, ...}, ...]
    """
    from bbsbot.mcp.server import session_manager

    # Get active bot
    bot = None
    for session_id in session_manager._sessions:
        bot = session_manager.get_bot(session_id)
        if bot:
            break

    if not bot:
        return []

    # Check if bot has strategy with find_opportunities
    if not hasattr(bot, "strategy") or not bot.strategy:
        return []

    strategy = bot.strategy
    if not hasattr(strategy, "find_opportunities"):
        return []

    # Get current state
    if not bot.game_state:
        return []

    # Find opportunities
    try:
        opportunities = strategy.find_opportunities(bot.game_state)

        # Filter and format
        results = []
        for opp in opportunities:
            if opp.expected_profit >= min_profit and opp.distance <= max_hops:
                results.append({
                    "buy_sector": opp.buy_sector,
                    "sell_sector": opp.sell_sector,
                    "commodity": opp.commodity,
                    "expected_profit": opp.expected_profit,
                    "distance": opp.distance,
                    "profit_per_turn": opp.profit_per_turn,
                    "confidence": opp.confidence,
                })

        return results
    except Exception as e:
        logger.error(f"trade_opportunities_error: {e}")
        return []


@registry.tool()
async def analyze_combat_readiness() -> dict[str, Any]:
    """Assess combat capability and recommend upgrades.

    Evaluates the bot's current military strength based on fighters,
    shields, and available credits. Provides upgrade recommendations.

    Returns:
        Combat stats and upgrade recommendations

    Example:
        status = await tw2002_analyze_combat_readiness()
        # Returns: {fighters: 45, shields: 120, readiness: "moderate", ...}
    """
    from bbsbot.mcp.server import session_manager

    # Get active bot
    bot = None
    for session_id in session_manager._sessions:
        bot = session_manager.get_bot(session_id)
        if bot:
            break

    if not bot:
        return {
            "error": "No active bot found",
        }

    if not bot.game_state:
        return {
            "error": "No game state available",
        }

    state = bot.game_state

    # Assess readiness
    fighters = state.fighters or 0
    shields = state.shields or 0
    credits = state.credits or 0

    # Simple readiness calculation
    if fighters >= 100 and shields >= 200:
        readiness = "high"
    elif fighters >= 50 and shields >= 100:
        readiness = "moderate"
    else:
        readiness = "low"

    # Recommendations
    recommendations = []
    if fighters < 100:
        recommendations.append({
            "type": "fighters",
            "current": fighters,
            "recommended": 100,
            "cost_estimate": (100 - fighters) * 50,  # Rough estimate
        })

    if shields < 200:
        recommendations.append({
            "type": "shields",
            "current": shields,
            "recommended": 200,
            "cost_estimate": (200 - shields) * 30,  # Rough estimate
        })

    return {
        "fighters": fighters,
        "shields": shields,
        "credits": credits,
        "readiness": readiness,
        "recommendations": recommendations,
    }


@registry.tool()
async def get_bot_status() -> dict[str, Any]:
    """Get comprehensive bot status (combines multiple stats).

    Returns current game state, strategy info, goals, progress,
    and resource levels in a single call.

    Returns:
        Comprehensive bot status

    Example:
        status = await tw2002_get_bot_status()
        # Returns: {goal: "profit", sector: 100, credits: 50000, ...}
    """
    from bbsbot.mcp.server import session_manager

    # Get active bot
    bot = None
    bot_session_id = None
    for session_id in session_manager._sessions:
        bot = session_manager.get_bot(session_id)
        if bot:
            bot_session_id = session_id
            break

    if not bot:
        return {
            "connected": False,
            "error": "No active bot found",
        }

    result: dict[str, Any] = {
        "connected": True,
        "session_id": bot_session_id,
        "character_name": getattr(bot, "character_name", "unknown"),
    }

    # Strategy info
    if hasattr(bot, "strategy") and bot.strategy:
        strategy = bot.strategy
        result["strategy"] = {
            "name": strategy.name,
            "type": type(strategy).__name__,
        }

        # Goal info (if supported)
        if hasattr(strategy, "get_current_goal"):
            result["goal"] = {
                "current": strategy.get_current_goal(),
                "turn": strategy._current_turn,
            }

    # Game state
    if hasattr(bot, "game_state") and bot.game_state:
        gs = bot.game_state
        result["game_state"] = {
            "context": gs.context,
            "sector": gs.sector,
            "credits": gs.credits,
            "turns_left": gs.turns_left,
            "fighters": gs.fighters,
            "shields": gs.shields,
            "holds_free": gs.holds_free,
            "holds_total": gs.holds_total,
            "has_port": gs.has_port,
        }

    # Progress
    result["progress"] = {
        "cycles": getattr(bot, "cycle_count", 0),
        "errors": getattr(bot, "error_count", 0),
        "trades": len(getattr(bot, "trade_history", [])),
        "sectors_visited": len(getattr(bot, "sectors_visited", set())),
    }

    return result
