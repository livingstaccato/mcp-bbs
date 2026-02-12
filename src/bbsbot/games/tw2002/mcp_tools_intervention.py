# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TW2002 intervention system MCP tools.

Provides MCP tools for monitoring and controlling the intervention system.
"""

from __future__ import annotations

from typing import Any

from bbsbot.games.tw2002.mcp_context import resolve_active_bot
from bbsbot.logging import get_logger
from bbsbot.mcp.registry import create_registry

logger = get_logger(__name__)

# Create intervention tool registry
registry = create_registry("tw2002_intervention")


def _get_active_bot() -> Any:
    """Get the currently active bot instance."""
    bot, _, _ = resolve_active_bot()
    return bot


@registry.tool()
async def get_intervention_status() -> dict[str, Any]:
    """Get intervention system status and recent alerts.

    Returns the current state of the intervention monitoring system,
    including detection statistics, recent anomalies, opportunities,
    and intervention history.

    Returns:
        Intervention system status and statistics

    Example:
        status = await tw2002_intervention_get_intervention_status()
        # Returns: {enabled: true, interventions_this_session: 3, ...}
    """
    bot = _get_active_bot()

    if not bot:
        return {"enabled": False, "error": "No active bot found"}

    if not hasattr(bot, "strategy") or not bot.strategy:
        return {"enabled": False, "error": "Bot has no strategy"}

    strategy = bot.strategy
    if not hasattr(strategy, "_intervention_trigger"):
        return {"enabled": False, "error": "Strategy has no intervention system"}

    trigger = strategy._intervention_trigger

    if not trigger.enabled:
        return {"enabled": False}

    # Build status
    result = {
        "enabled": True,
        "interventions_this_session": trigger.interventions_this_session,
        "budget_remaining": trigger.budget_remaining,
        "last_intervention_turn": trigger.detector._last_intervention_turn,
    }

    # Recent anomalies
    anomalies = trigger.detector.recent_anomalies
    result["recent_anomalies"] = [
        {
            "type": a.type.value,
            "priority": a.priority.value,
            "confidence": a.confidence,
            "description": a.description,
            "evidence": a.evidence,
        }
        for a in anomalies[-5:]
    ]

    # Recent opportunities
    opportunities = trigger.detector.recent_opportunities
    result["recent_opportunities"] = [
        {
            "type": o.type.value,
            "priority": o.priority.value,
            "confidence": o.confidence,
            "description": o.description,
            "evidence": o.evidence,
        }
        for o in opportunities[-5:]
    ]

    # Turn history summary
    history = trigger.detector.turn_history
    if history:
        result["turn_history_summary"] = {
            "turns_tracked": len(history),
            "recent_actions": [t.action for t in history[-5:]],
            "recent_sectors": [t.sector for t in history[-5:]],
            "total_profit": sum(t.profit_delta for t in history),
        }

    return result


@registry.tool()
async def trigger_manual_intervention(analysis_prompt: str | None = None) -> dict[str, Any]:
    """Manually trigger intervention analysis.

    Forces the intervention system to analyze current bot behavior
    and provide recommendations, bypassing normal cooldown and trigger
    conditions. Optionally provide a custom analysis prompt.

    Args:
        analysis_prompt: Optional custom prompt for analysis focus

    Returns:
        Intervention analysis and recommendation

    Example:
        result = await tw2002_intervention_trigger_manual_intervention()
        # Forces immediate intervention analysis

        result = await tw2002_intervention_trigger_manual_intervention(
            analysis_prompt="Why is the bot stuck in sector 100?"
        )
        # Analyzes with custom prompt
    """
    bot = _get_active_bot()

    if not bot:
        return {"success": False, "error": "No active bot found"}

    if not hasattr(bot, "strategy") or not bot.strategy:
        return {"success": False, "error": "Bot has no strategy"}

    strategy = bot.strategy
    if not hasattr(strategy, "_intervention_trigger") or not hasattr(strategy, "_intervention_advisor"):
        return {"success": False, "error": "Strategy has no intervention system"}

    trigger = strategy._intervention_trigger
    advisor = strategy._intervention_advisor

    if not trigger.enabled:
        return {"success": False, "error": "Intervention system is disabled"}

    # Get current state
    game_state = getattr(bot, "game_state", None)
    if not game_state:
        return {"success": False, "error": "No game state available"}

    # Force detection
    anomalies = trigger.detector.detect_anomalies(
        current_turn=strategy._current_turn,
        state=game_state,
        strategy=strategy,
    )
    opportunities = trigger.detector.detect_opportunities(
        current_turn=strategy._current_turn,
        state=game_state,
        strategy=strategy,
    )

    # Build trigger reason
    reason = analysis_prompt or "Manual intervention triggered"
    if anomalies or opportunities:
        items = []
        if anomalies:
            items.append(f"{len(anomalies)} anomalies")
        if opportunities:
            items.append(f"{len(opportunities)} opportunities")
        reason = f"Manual trigger: {', '.join(items)}"

    # Query LLM for analysis
    try:
        recommendation = await advisor.analyze(
            state=game_state,
            recent_decisions=strategy._get_recent_decisions(),
            strategy_stats=strategy.stats,
            goal_phases=strategy._goal_phases,
            anomalies=[a.model_dump() for a in anomalies],
            opportunities=[o.model_dump() for o in opportunities],
            trigger_reason=reason,
        )

        # Log intervention (but don't count against budget for manual triggers)
        context = {
            "anomalies": [a.model_dump() for a in anomalies],
            "opportunities": [o.model_dump() for o in opportunities],
            "turn": strategy._current_turn,
            "manual": True,
        }

        await trigger.log_intervention(
            turn=strategy._current_turn,
            reason=reason,
            context=context,
            recommendation=recommendation,
        )

        return {
            "success": True,
            "reason": reason,
            "anomalies_detected": len(anomalies),
            "opportunities_detected": len(opportunities),
            "recommendation": recommendation,
        }

    except Exception as e:
        logger.error("Manual intervention failed", error=str(e))
        return {
            "success": False,
            "error": f"Analysis failed: {e}",
        }
