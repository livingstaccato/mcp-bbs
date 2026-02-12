# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Intervention advisor for LLM-based analysis.

This module builds intervention-specific prompts and queries the LLM
for strategic analysis and recommendations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bbsbot.llm.types import ChatMessage, ChatRequest
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import GameState
    from bbsbot.llm.manager import LLMManager

logger = get_logger(__name__)

INTERVENTION_SYSTEM_PROMPT = """You are an expert Trade Wars 2002 gameplay analyst monitoring autonomous bot performance.

YOUR ROLE: Detect behavioral anomalies, performance degradation, and missed opportunities.

CRITICAL PRIORITY - COMPLETE STAGNATION:
If the bot has made NO changes (same sector, same credits, no events) for multiple turns,
this is a CRITICAL failure. The bot is completely stuck and needs immediate strategic reorientation:
- Suggest changing to exploration goal to discover new sectors
- Recommend force_move to a known port or trading hub
- Propose reset_strategy to clear any stuck state
- Identify WHY the bot is stuck (no warps? no fuel? invalid strategy?)

ANALYSIS FRAMEWORK:

1. PATTERN RECOGNITION
   - COMPLETE STAGNATION (CRITICAL): No changes in sector, credits, or events
   - Stuck behaviors (repeated actions, location loops)
   - Efficiency drops (declining profit velocity, wasted turns)
   - Goal misalignment (actions inconsistent with stated goal)
   - Decision quality issues (poor reasoning, invalid assumptions)

2. OPPORTUNITY DETECTION
   - Overlooked profitable trades
   - Combat readiness gaps
   - Banking failures (excess credits not secured)
   - Exploration inefficiencies

3. SEVERITY ASSESSMENT
   - CRITICAL: Bot completely stuck (no changes), ship at risk, or major capital loss
   - WARNING: Performance declining, suboptimal patterns
   - INFO: Minor inefficiencies, optimization opportunities

OUTPUT FORMAT (strict JSON):
{
  "severity": "critical|warning|info",
  "category": "stuck_pattern|performance_decline|opportunity_missed|goal_misalignment",
  "observation": "Concise issue description (1-2 sentences)",
  "evidence": ["Supporting fact 1", "Supporting fact 2", ...],
  "recommendation": "continue|adjust_goal|manual_review|direct_intervention",
  "suggested_action": {
    "type": "change_goal|reset_strategy|force_move|none",
    "parameters": {...}
  },
  "reasoning": "Why this recommendation (2-3 sentences)",
  "confidence": 0.0-1.0
}

Keep analysis focused and actionable. Prioritize critical issues over optimizations."""


class InterventionAdvisor:
    """Builds intervention prompts and queries LLM for recommendations."""

    def __init__(
        self,
        config: BotConfig,
        llm_manager: LLMManager,
    ) -> None:
        """Initialize advisor.

        Args:
            config: Bot configuration
            llm_manager: LLM manager for queries
        """
        self.config = config
        self.llm_manager = llm_manager

    async def analyze(
        self,
        state: GameState,
        recent_decisions: list[dict[str, Any]],
        strategy_stats: dict[str, Any],
        goal_phases: list[Any],
        anomalies: list[dict[str, Any]],
        opportunities: list[dict[str, Any]],
        trigger_reason: str,
    ) -> dict[str, Any]:
        """Build prompt and query LLM for intervention analysis.

        Args:
            state: Current game state
            recent_decisions: Recent decision history with reasoning
            strategy_stats: Strategy performance statistics
            goal_phases: Goal history with metrics
            anomalies: Detected anomalies
            opportunities: Detected opportunities
            trigger_reason: Human-readable trigger reason

        Returns:
            Dict with LLM recommendation
        """
        prompt = self._build_prompt(
            state=state,
            recent_decisions=recent_decisions,
            strategy_stats=strategy_stats,
            goal_phases=goal_phases,
            anomalies=anomalies,
            opportunities=opportunities,
            trigger_reason=trigger_reason,
        )

        logger.info(
            "Requesting intervention analysis",
            trigger_reason=trigger_reason,
            anomaly_count=len(anomalies),
            opportunity_count=len(opportunities),
        )

        # Build chat request with intervention system prompt
        messages = [
            ChatMessage(role="system", content=INTERVENTION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ]

        request = ChatRequest(
            messages=messages,
            model=self.config.llm.ollama.model,
            temperature=self.config.trading.ai_strategy.intervention.analysis_temperature,
            max_tokens=self.config.trading.ai_strategy.intervention.analysis_max_tokens,
        )

        # Query LLM
        response = await self.llm_manager.chat(request)

        # Parse response
        try:
            import json
            from typing import cast

            recommendation = cast("dict[str, Any]", json.loads(response.message.content))
            logger.info(
                "Received intervention recommendation",
                severity=recommendation.get("severity"),
                recommendation_type=recommendation.get("recommendation"),
            )
            return recommendation
        except json.JSONDecodeError as e:
            logger.error("Failed to parse intervention response", error=str(e))
            return {
                "severity": "info",
                "category": "parse_error",
                "observation": "Failed to parse LLM response",
                "evidence": [str(e)],
                "recommendation": "continue",
                "suggested_action": {"type": "none", "parameters": {}},
                "reasoning": "Parse error, continuing with current strategy",
                "confidence": 0.0,
            }

    def _build_prompt(
        self,
        state: GameState,
        recent_decisions: list[dict[str, Any]],
        strategy_stats: dict[str, Any],
        goal_phases: list[Any],
        anomalies: list[dict[str, Any]],
        opportunities: list[dict[str, Any]],
        trigger_reason: str,
    ) -> str:
        """Build intervention analysis prompt.

        Args:
            state: Current game state
            recent_decisions: Recent decision history
            strategy_stats: Strategy statistics
            goal_phases: Goal history
            anomalies: Detected anomalies
            opportunities: Detected opportunities
            trigger_reason: Trigger reason

        Returns:
            Formatted prompt string
        """
        # Build goal context
        goal_context = "No goal history available"
        if goal_phases:
            current_phase = goal_phases[-1]
            goal_context = f"""
- Current Goal: {getattr(current_phase, "goal_id", "unknown")}
- Duration: {getattr(current_phase, "turns", 0)} turns
- Start Credits: {getattr(current_phase, "start_credits", 0):,}
- Current Credits: {state.credits:,}
- Net Change: {state.credits - getattr(current_phase, "start_credits", 0):+,}
"""

        # Build performance metrics
        profit_per_turn = strategy_stats.get("profit_per_turn", 0)
        trades_executed = strategy_stats.get("trades_executed", 0)

        # Format anomalies
        anomaly_text = "None detected"
        if anomalies:
            anomaly_lines = []
            for a in anomalies:
                anomaly_lines.append(f"  - [{a['priority'].upper()}] {a['type']}: {a['description']}")
                for evidence in a.get("evidence", []):
                    anomaly_lines.append(f"    • {evidence}")
            anomaly_text = "\n".join(anomaly_lines)

        # Format opportunities
        opportunity_text = "None detected"
        if opportunities:
            opp_lines = []
            for o in opportunities:
                opp_lines.append(f"  - [{o['priority'].upper()}] {o['type']}: {o['description']}")
                for evidence in o.get("evidence", []):
                    opp_lines.append(f"    • {evidence}")
            opportunity_text = "\n".join(opp_lines)

        # Format recent decisions
        decision_text = "No recent decisions"
        if recent_decisions:
            decision_lines = []
            for i, d in enumerate(recent_decisions[-5:], 1):
                action = d.get("action", "unknown")
                reasoning = d.get("reasoning", "no reasoning provided")
                profit = d.get("profit_delta", 0)
                decision_lines.append(f"  {i}. {action} (profit: {profit:+,}) - {reasoning}")
            decision_text = "\n".join(decision_lines)

        # Build full prompt
        prompt = f"""INTERVENTION ANALYSIS REQUEST
Trigger: {trigger_reason}

CURRENT STATE:
- Location: Sector {state.current_sector}
- Credits: {state.credits:,}
- Ship: {state.holds_free}/{state.holds_total} holds free, {state.fighters} fighters, {state.shields} shields
- Turns: {state.turns_remaining} remaining

GOAL CONTEXT:{goal_context}

PERFORMANCE METRICS:
- Profit/Turn: {profit_per_turn:.1f}
- Trades Executed: {trades_executed}

ANOMALIES DETECTED:
{anomaly_text}

OPPORTUNITIES IDENTIFIED:
{opportunity_text}

RECENT DECISIONS (with reasoning):
{decision_text}

Analyze and provide your assessment in JSON format."""

        return prompt


def format_anomalies(anomalies: list[dict[str, Any]]) -> str:
    """Format anomalies for display."""
    if not anomalies:
        return "None detected"

    lines = []
    for a in anomalies:
        lines.append(f"  - [{a['priority'].upper()}] {a['type']}: {a['description']}")
        for evidence in a.get("evidence", []):
            lines.append(f"    • {evidence}")
    return "\n".join(lines)


def format_opportunities(opportunities: list[dict[str, Any]]) -> str:
    """Format opportunities for display."""
    if not opportunities:
        return "None detected"

    lines = []
    for o in opportunities:
        lines.append(f"  - [{o['priority'].upper()}] {o['type']}: {o['description']}")
        for evidence in o.get("evidence", []):
            lines.append(f"    • {evidence}")
    return "\n".join(lines)
