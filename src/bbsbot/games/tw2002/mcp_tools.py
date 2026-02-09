"""TW2002-specific MCP tools.

Provides game-specific functionality accessible via MCP interface.
Tools are prefixed with 'tw2002_' to distinguish from core bbs_ tools.
"""

from __future__ import annotations

from typing import Any

from bbsbot.logging import get_logger
from bbsbot.mcp.registry import create_registry

logger = get_logger(__name__)

# Create TW2002 tool registry
registry = create_registry("tw2002")

# Import other tool modules to register their tools
# Import is placed after registry creation so they can use it
from bbsbot.games.tw2002 import (  # noqa: E402, F401
    mcp_tools_control,
    mcp_tools_goals,
    mcp_tools_intervention,
)


def _get_active_bot():
    from bbsbot.mcp.server import session_manager

    bot = None
    for session_id in session_manager._sessions:
        bot = session_manager.get_bot(session_id)
        if bot:
            break
    return bot


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
                results.append(
                    {
                        "buy_sector": opp.buy_sector,
                        "sell_sector": opp.sell_sector,
                        "commodity": opp.commodity,
                        "expected_profit": opp.expected_profit,
                        "distance": opp.distance,
                        "profit_per_turn": opp.profit_per_turn,
                        "confidence": opp.confidence,
                    }
                )

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
        recommendations.append(
            {
                "type": "fighters",
                "current": fighters,
                "recommended": 100,
                "cost_estimate": (100 - fighters) * 50,  # Rough estimate
            }
        )

    if shields < 200:
        recommendations.append(
            {
                "type": "shields",
                "current": shields,
                "recommended": 200,
                "cost_estimate": (200 - shields) * 30,  # Rough estimate
            }
        )

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


@registry.tool()
async def debug(command: str, limit: int | None = None) -> dict[str, Any]:
    """Debug proxy that delegates to BBS debugging tools.

    This is a convenience wrapper around bbs_debug_* tools that provides
    game-aware defaults and simplified API.

    Args:
        command: Debug command to run. Options:
            - 'bot_state': Get bot runtime state
            - 'learning_state': Get learning engine state
            - 'llm_stats': Get LLM usage statistics
            - 'session_events': Query recent session events
        limit: Optional limit parameter for session_events query (default: None)

    Returns:
        Result from underlying debug tool

    Examples:
        await tw2002_debug(command='bot_state')
        await tw2002_debug(command='session_events', limit=10)
    """
    from bbsbot.mcp.server import (
        bbs_debug_bot_state,
        bbs_debug_learning_state,
        bbs_debug_llm_stats,
        bbs_debug_session_events,
    )

    match command:
        case "bot_state":
            return await bbs_debug_bot_state()
        case "learning_state":
            return await bbs_debug_learning_state()
        case "llm_stats":
            return await bbs_debug_llm_stats()
        case "session_events":
            if limit is not None:
                return await bbs_debug_session_events(limit=limit)
            return await bbs_debug_session_events()
        case _:
            raise ValueError(
                f"Unknown command: {command}. "
                f"Valid options: bot_state, learning_state, llm_stats, session_events"
            )
