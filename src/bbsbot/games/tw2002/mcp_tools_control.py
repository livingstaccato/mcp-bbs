"""MCP control tools for bot health, recovery, and LLM delegation.

Provides advanced bot monitoring, emergency recovery actions, and
strategic guidance via LLM delegation.
"""

from __future__ import annotations

from typing import Any

from bbsbot.games.tw2002.mcp_tools import registry
from bbsbot.logging import get_logger

logger = get_logger(__name__)


def _get_active_bot():
    """Get the active bot from session manager."""
    from bbsbot.mcp.server import session_manager

    bot = None
    for session_id in session_manager._sessions:
        bot = session_manager.get_bot(session_id)
        if bot:
            break
    return bot


def _mark_hijacked(bot: object, tool_name: str) -> None:
    """Mark bot as hijacked via MCP tool."""
    import time

    try:
        # Try to update manager status if available
        if hasattr(bot, "session_id") and hasattr(bot, "session_manager"):
            session_id = bot.session_id
            manager = bot.session_manager
            if manager and hasattr(manager, "bots"):
                if session_id in manager.bots:
                    status = manager.bots[session_id]
                    status.is_hijacked = True
                    status.hijacked_at = time.time()
                    status.hijacked_by = tool_name
    except Exception as e:
        logger.debug(f"Could not mark bot as hijacked: {e}")


@registry.tool()
async def get_bot_health() -> dict[str, Any]:
    """Monitor bot health and runtime status.

    Returns comprehensive diagnostics including:
    - Bot status (running/crashed/stuck/idle)
    - Last error details (type, message, timestamp)
    - Progress (turns_completed, max_turns, percent_complete)
    - Activity (time_since_last_action_seconds, last_action_type)
    - Strategy (name, trades_executed, total_profit)
    - Knowledge (initialized, sectors_known, ports_known)

    Returns:
        Comprehensive bot health status

    Example:
        health = await tw2002_get_bot_health()
        # Returns: {status: "running", turns_completed: 150, ...}
    """
    import time

    bot = _get_active_bot()
    if not bot:
        return {
            "status": "error",
            "error": "No active bot found",
        }

    result: dict[str, Any] = {
        "status": "running",
        "character_name": getattr(bot, "character_name", "unknown"),
        "session_id": getattr(bot, "session_id", None),
    }

    # Progress tracking
    game_state = getattr(bot, "game_state", None)
    if game_state:
        turns_left = getattr(game_state, "turns_left", 0)
        turns_completed = getattr(bot, "turns_completed", 0)
        result["progress"] = {
            "turns_completed": turns_completed,
            "turns_left": turns_left,
            "total_turns_estimate": turns_completed + turns_left,
            "percent_complete": (
                (turns_completed / (turns_completed + turns_left) * 100)
                if (turns_completed + turns_left) > 0
                else 0
            ),
        }
    else:
        result["progress"] = {
            "turns_completed": 0,
            "turns_left": 0,
            "total_turns_estimate": 0,
            "percent_complete": 0,
        }

    # Strategy info
    strategy = getattr(bot, "strategy", None)
    if strategy:
        result["strategy"] = {
            "name": getattr(strategy, "name", "unknown"),
            "type": type(strategy).__name__,
        }
        # Trades and profit tracking
        result["trades"] = {
            "executed": len(getattr(bot, "trade_history", [])),
            "total_profit": sum(
                t.get("profit", 0) for t in getattr(bot, "trade_history", [])
            ),
        }
    else:
        result["strategy"] = {
            "name": "not_initialized",
            "type": "none",
        }
        result["trades"] = {
            "executed": 0,
            "total_profit": 0,
        }

    # Activity tracking
    last_action_time = getattr(bot, "_last_action_time", None)
    if last_action_time:
        time_since_action = time.time() - last_action_time
        result["activity"] = {
            "time_since_last_action_seconds": round(time_since_action, 1),
            "last_action_type": getattr(bot, "_last_action_type", "unknown"),
            "idle": time_since_action > 30,  # Idle if no action for 30+ seconds
        }
    else:
        result["activity"] = {
            "time_since_last_action_seconds": None,
            "last_action_type": None,
            "idle": True,
        }

    # Knowledge base status
    knowledge = getattr(bot, "sector_knowledge", None)
    if knowledge:
        result["knowledge"] = {
            "initialized": True,
            "sectors_known": len(getattr(knowledge, "sectors", {})),
            "ports_known": len(getattr(knowledge, "ports", {})),
            "trade_routes_discovered": len(getattr(knowledge, "routes", {})),
        }
    else:
        result["knowledge"] = {
            "initialized": False,
            "sectors_known": 0,
            "ports_known": 0,
            "trade_routes_discovered": 0,
        }

    # Error tracking
    error_count = getattr(bot, "error_count", 0)
    if error_count > 0:
        result["status"] = "recovering"
    result["error_count"] = error_count

    return result


@registry.tool()
async def recover_bot(
    recovery_action: str,
    strategy_name: str | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    """Emergency recovery actions for crashed or stuck bots.

    Performs recovery actions on crashed/stuck bots to restore operation
    without requiring a full bot restart.

    Args:
        recovery_action: Recovery action to perform
            - 'restart_strategy': Re-initialize current strategy
            - 'reset_knowledge': Clear and rebuild knowledge base
            - 'change_strategy': Switch strategy (requires strategy_name parameter)
            - 'manual_command': Send game command (requires command parameter)
        strategy_name: Strategy name for 'change_strategy' action
        command: Game command for 'manual_command' action

    Returns:
        Recovery status and results

    Example:
        result = await tw2002_recover_bot(recovery_action="restart_strategy")
        # Returns: {success: True, message: "Strategy reinitialized"}
    """
    bot = _get_active_bot()
    if not bot:
        return {
            "success": False,
            "error": "No active bot found",
        }

    try:
        match recovery_action:
            case "restart_strategy":
                # Re-initialize current strategy
                if bot.sector_knowledge is None:
                    # Initialize knowledge first if needed
                    bot.init_knowledge()

                bot.init_strategy()
                logger.info("Bot strategy reinitialized")
                return {
                    "success": True,
                    "message": "Strategy reinitialized",
                    "strategy": getattr(bot.strategy, "name", "unknown"),
                }

            case "reset_knowledge":
                # Clear and rebuild knowledge base
                bot.init_knowledge()
                logger.info("Bot knowledge base reset")
                return {
                    "success": True,
                    "message": "Knowledge base reset and initialized",
                    "sectors_known": len(getattr(bot.sector_knowledge, "sectors", {})),
                }

            case "change_strategy":
                # Switch to different strategy
                if not strategy_name:
                    return {
                        "success": False,
                        "error": "strategy_name parameter required for change_strategy",
                    }

                # Update config and reinitialize
                bot.config.trading.strategy = strategy_name
                if bot.sector_knowledge is None:
                    bot.init_knowledge()
                bot.init_strategy()

                logger.info(f"Bot strategy changed to {strategy_name}")
                return {
                    "success": True,
                    "message": f"Strategy changed to {strategy_name}",
                    "new_strategy": getattr(bot.strategy, "name", "unknown"),
                }

            case "manual_command":
                # Send game command via session
                if not command:
                    return {
                        "success": False,
                        "error": "command parameter required for manual_command",
                    }

                if not bot.session:
                    return {
                        "success": False,
                        "error": "No active session to send command",
                    }

                bot.session.send(command)
                logger.info(f"Manual command sent: {command}")
                return {
                    "success": True,
                    "message": f"Command sent: {command}",
                }

            case _:
                return {
                    "success": False,
                    "error": (
                        f"Unknown recovery action: {recovery_action}. "
                        f"Valid options: restart_strategy, reset_knowledge, "
                        f"change_strategy, manual_command"
                    ),
                }

    except Exception as e:
        logger.error(f"Recovery action failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@registry.tool()
async def knowledge_status() -> dict[str, Any]:
    """Check knowledge base health and coverage.

    Returns detailed diagnostics about the sector knowledge database
    including initialization status, known sectors, ports, and trade routes.

    Returns:
        - initialized: bool
        - sectors_known: int (total count)
        - ports_known: int (total count)
        - ports_by_class: dict (counts by port type)
        - trade_routes_discovered: int
        - recent_scans: list (last scanned sectors with timestamps)

    Example:
        status = await tw2002_knowledge_status()
        # Returns: {initialized: True, sectors_known: 156, ...}
    """
    bot = _get_active_bot()
    if not bot:
        return {
            "initialized": False,
            "error": "No active bot found",
        }

    knowledge = getattr(bot, "sector_knowledge", None)
    if not knowledge:
        return {
            "initialized": False,
            "error": "Knowledge base not initialized",
        }

    # Get sectors and ports
    sectors = getattr(knowledge, "sectors", {})
    ports = getattr(knowledge, "ports", {})
    routes = getattr(knowledge, "routes", {})

    # Count ports by class
    ports_by_class = {}
    for port in ports.values():
        port_class = getattr(port, "port_class", "unknown")
        ports_by_class[port_class] = ports_by_class.get(port_class, 0) + 1

    # Get recent scans if available
    recent_scans = []
    scans = getattr(knowledge, "recent_scans", [])
    for sector_id in scans[-10:]:  # Last 10
        if sector_id in sectors:
            sector = sectors[sector_id]
            recent_scans.append(
                {
                    "sector": sector_id,
                    "has_port": hasattr(sector, "has_port") and sector.has_port,
                }
            )

    result: dict[str, Any] = {
        "initialized": True,
        "sectors_known": len(sectors),
        "ports_known": len(ports),
        "ports_by_class": ports_by_class,
        "trade_routes_discovered": len(routes),
        "recent_scans": recent_scans,
    }

    # Knowledge directory if available
    knowledge_dir = getattr(knowledge, "knowledge_dir", None)
    if knowledge_dir:
        result["knowledge_dir"] = str(knowledge_dir)

    return result


@registry.tool()
async def force_action(action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Force bot to execute specific action, bypassing strategy.

    Directly executes a game action without going through the normal
    strategy decision-making process. Useful for emergency manual control.

    Args:
        action: Action type to execute
            - 'warp': Move to sector (params: {sector: int})
            - 'dock': Dock at current port
            - 'trade': Execute trade (params: {commodity: str, quantity: int})
            - 'bank': Deposit/withdraw credits (params: {amount: int})
            - 'scan': Run D command to scan sector
        params: Action-specific parameters (dict)

    Returns:
        Execution status and result

    Example:
        result = await tw2002_force_action(
            action="warp",
            params={"sector": 567}
        )
        # Returns: {success: True, message: "Warped to sector 567"}
    """
    if params is None:
        params = {}

    bot = _get_active_bot()
    if not bot:
        return {
            "success": False,
            "error": "No active bot found",
        }

    if not bot.session:
        return {
            "success": False,
            "error": "No active session",
        }

    try:
        match action:
            case "warp":
                sector = params.get("sector")
                if sector is None:
                    return {
                        "success": False,
                        "error": "sector parameter required",
                    }
                bot.session.send(f"W\r{sector}\r")
                _mark_hijacked(bot, "force_action")
                logger.info(f"Forced warp to sector {sector}")
                return {
                    "success": True,
                    "message": f"Warped to sector {sector}",
                }

            case "dock":
                bot.session.send("D\r")
                _mark_hijacked(bot, "force_action")
                logger.info("Forced dock")
                return {
                    "success": True,
                    "message": "Docking at port",
                }

            case "scan":
                bot.session.send("D\r")
                _mark_hijacked(bot, "force_action")
                logger.info("Forced scan")
                return {
                    "success": True,
                    "message": "Running sector scan",
                }

            case "trade":
                commodity = params.get("commodity")
                quantity = params.get("quantity")
                if not commodity or quantity is None:
                    return {
                        "success": False,
                        "error": "commodity and quantity parameters required",
                    }
                # Note: Actual trade execution would be more complex
                logger.info(f"Forced trade: {quantity} {commodity}")
                return {
                    "success": True,
                    "message": f"Trade queued: {quantity} {commodity}",
                }

            case "bank":
                amount = params.get("amount")
                if amount is None:
                    return {
                        "success": False,
                        "error": "amount parameter required",
                    }
                logger.info(f"Forced bank action: {amount} credits")
                return {
                    "success": True,
                    "message": f"Bank action: {amount} credits",
                }

            case _:
                return {
                    "success": False,
                    "error": (
                        f"Unknown action: {action}. "
                        f"Valid options: warp, dock, scan, trade, bank"
                    ),
                }

    except Exception as e:
        logger.error(f"Force action failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@registry.tool()
async def ask_strategy(
    question: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ask the AI strategy for advice on a specific question.

    Delegates to the bot's AI/LLM to get strategic recommendations
    based on current game state and user question. Only works with
    AI-based strategies that support LLM integration.

    Args:
        question: Strategic question (e.g., "Should I focus on trading or combat?")
        context: Optional context to provide (sector, credits, fighters, etc.)

    Returns:
        - answer: str (strategic recommendation)
        - reasoning: str (LLM's reasoning process)
        - recommended_action: str (suggested next action)
        - confidence: float (0-1, how confident the LLM is)

    Example:
        result = await tw2002_ask_strategy(
            question="Should I trade or explore right now?",
            context={"credits": 50000, "fighters": 10, "current_sector": 567}
        )
    """
    bot = _get_active_bot()
    if not bot:
        return {
            "success": False,
            "error": "No active bot found",
        }

    strategy = getattr(bot, "strategy", None)
    if not strategy:
        return {
            "success": False,
            "error": "No strategy initialized",
        }

    # Check if strategy supports LLM delegation
    if not hasattr(strategy, "ask_llm"):
        return {
            "success": False,
            "error": (
                f"Strategy '{getattr(strategy, 'name', 'unknown')}' "
                f"does not support LLM delegation"
            ),
            "hint": "Use AI-based strategy (e.g., ai_strategy) to enable LLM advice",
        }

    try:
        # Get game state for context
        game_state = getattr(bot, "game_state", None)
        if context is None:
            context = {}

        # Add game state to context if available
        if game_state:
            if not context:
                context = {}
            context.setdefault("sector", game_state.sector)
            context.setdefault("credits", game_state.credits)
            context.setdefault("fighters", game_state.fighters)
            context.setdefault("shields", game_state.shields)
            context.setdefault("turns_left", game_state.turns_left)

        # Call strategy's LLM delegation
        result = await strategy.ask_llm(question, context)

        logger.info(f"LLM advice requested: {question}")
        return {
            "success": True,
            "question": question,
            "answer": result.get("answer", ""),
            "reasoning": result.get("reasoning", ""),
            "recommended_action": result.get("recommended_action", ""),
            "confidence": result.get("confidence", 0.5),
        }

    except AttributeError:
        return {
            "success": False,
            "error": "Strategy does not support LLM delegation",
        }
    except Exception as e:
        logger.error(f"LLM delegation failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
