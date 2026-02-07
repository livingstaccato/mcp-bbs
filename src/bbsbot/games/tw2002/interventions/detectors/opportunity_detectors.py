"""Opportunity detection algorithms for intervention system.

Implements detection methods for missed opportunities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.games.tw2002.interventions.types import (
    InterventionPriority,
    Opportunity,
    OpportunityType,
)

if TYPE_CHECKING:
    from bbsbot.games.tw2002.orientation import GameState
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy


def detect_high_value_trade(state: GameState, strategy: AIStrategy) -> Opportunity | None:
    """Detect high-value trade opportunities."""
    # This would integrate with strategy.find_opportunities()
    # For now, return None as placeholder
    return None


def detect_combat_ready(state: GameState, strategy: AIStrategy) -> Opportunity | None:
    """Detect combat readiness."""
    # Check if ship is combat-ready but goal is not combat
    if state.fighters and state.fighters >= 50 and state.shields and state.shields >= 100:
        current_goal = getattr(strategy, "_current_goal_id", None)
        if current_goal != "combat":
            return Opportunity(
                type=OpportunityType.COMBAT_READY,
                priority=InterventionPriority.MEDIUM,
                confidence=0.8,
                description="Ship is combat-ready but not pursuing combat",
                evidence=[
                    f"Fighters: {state.fighters}",
                    f"Shields: {state.shields}",
                    f"Current goal: {current_goal}",
                ],
                metadata={
                    "fighters": state.fighters,
                    "shields": state.shields,
                    "current_goal": current_goal,
                },
            )

    return None


def detect_banking_optimal(state: GameState) -> Opportunity | None:
    """Detect optimal banking moment."""
    # Check if carrying significant credits outside FedSpace
    if state.credits and state.credits >= 100000:
        # Would need to check if in FedSpace - placeholder for now
        return Opportunity(
            type=OpportunityType.BANKING_OPTIMAL,
            priority=InterventionPriority.MEDIUM,
            confidence=0.85,
            description="Carrying >100k credits - consider banking",
            evidence=[
                f"Credits: {state.credits:,}",
                "Banking recommended for security",
            ],
            metadata={"credits": state.credits},
        )

    return None
