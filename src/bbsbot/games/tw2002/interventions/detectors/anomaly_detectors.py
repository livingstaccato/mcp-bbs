"""Anomaly detection algorithms for intervention system.

Implements detection methods for behavioral anomalies.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from bbsbot.games.tw2002.interventions.types import (
    Anomaly,
    AnomalyType,
    InterventionPriority,
    TurnData,
)

if TYPE_CHECKING:
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy


def detect_complete_stagnation(turn_history: list[TurnData]) -> Anomaly | None:
    """Detect COMPLETE stagnation - bot making NO progress at all.

    This is CRITICAL - the bot is truly stuck and needs immediate intervention.
    Checks for:
    - No sector changes
    - No credit changes
    - Same action repeated
    - No profit from any turns
    """
    if len(turn_history) < 5:
        return None

    # Check if ALL sectors are the same
    sectors = {t.sector for t in turn_history}
    if len(sectors) != 1:
        return None  # Moving between sectors, not completely stuck

    # Check if credits have changed AT ALL
    credits = {t.credits for t in turn_history}
    if len(credits) != 1:
        return None  # Credits changing, some activity

    # Check if ALL actions are the same
    actions = {t.action for t in turn_history}
    if len(actions) == 1:
        repeated_action = list(actions)[0]
        # Bot is repeating the SAME action in the SAME sector with NO credit change
        return Anomaly(
            type=AnomalyType.COMPLETE_STAGNATION,
            priority=InterventionPriority.CRITICAL,
            confidence=0.95,
            description=f"Bot completely stuck: {len(turn_history)} turns with NO changes",
            evidence=[
                f"Stuck in sector {turn_history[0].sector} for {len(turn_history)} turns",
                f"Repeating action: {repeated_action}",
                f"Credits unchanged: {turn_history[0].credits:,}",
                "No progress whatsoever - CRITICAL",
            ],
            metadata={
                "sector": turn_history[0].sector,
                "action": repeated_action,
                "credits": turn_history[0].credits,
                "turns_stuck": len(turn_history),
            },
        )

    # Even if actions vary, if sector and credits are identical, still concerning
    if len(turn_history) >= 7:  # More turns required for this case
        return Anomaly(
            type=AnomalyType.COMPLETE_STAGNATION,
            priority=InterventionPriority.CRITICAL,
            confidence=0.9,
            description=f"Bot stuck: {len(turn_history)} turns, same sector and credits",
            evidence=[
                f"Stuck in sector {turn_history[0].sector}",
                f"Credits unchanged: {turn_history[0].credits:,}",
                f"Actions: {[t.action for t in turn_history[-5:]]}",
                "No net progress - needs reorientation",
            ],
            metadata={
                "sector": turn_history[0].sector,
                "credits": turn_history[0].credits,
                "turns_stuck": len(turn_history),
                "actions": [t.action for t in turn_history],
            },
        )

    return None


def detect_action_loop(turn_history: list[TurnData]) -> Anomaly | None:
    """Detect repeated action patterns."""
    if len(turn_history) < 3:
        return None

    recent_actions = [t.action for t in turn_history[-5:]]

    # Check for same action repeated 3+ times
    action_counts = Counter(recent_actions)
    for action, count in action_counts.items():
        if count >= 3:
            return Anomaly(
                type=AnomalyType.ACTION_LOOP,
                priority=InterventionPriority.HIGH,
                confidence=0.85,
                description=f"Repeating {action} action {count} times",
                evidence=[
                    f"Last 5 actions: {' → '.join(recent_actions)}",
                    f"{action} repeated {count} times",
                ],
                metadata={"action": action, "count": count},
            )

    # Check for alternating pattern (A-B-A-B)
    if (
        len(recent_actions) >= 4
        and recent_actions[0] == recent_actions[2]
        and recent_actions[1] == recent_actions[3]
        and recent_actions[0] != recent_actions[1]
    ):
        return Anomaly(
            type=AnomalyType.ACTION_LOOP,
            priority=InterventionPriority.HIGH,
            confidence=0.8,
            description=f"Alternating pattern: {recent_actions[0]}-{recent_actions[1]}",
            evidence=[
                f"Last 5 actions: {' → '.join(recent_actions)}",
                "Alternating between two actions",
            ],
            metadata={
                "action_a": recent_actions[0],
                "action_b": recent_actions[1],
            },
        )

    return None


def detect_sector_loop(turn_history: list[TurnData]) -> Anomaly | None:
    """Detect circling between same sectors."""
    if len(turn_history) < 4:
        return None

    recent_sectors = [t.sector for t in turn_history]
    sector_counts = Counter(recent_sectors)

    # Check if any sector visited 4+ times
    for sector, count in sector_counts.items():
        if count >= 4:
            return Anomaly(
                type=AnomalyType.SECTOR_LOOP,
                priority=InterventionPriority.HIGH,
                confidence=0.8,
                description=f"Visiting sector {sector} repeatedly ({count} times)",
                evidence=[
                    f"Recent sectors: {recent_sectors}",
                    f"Sector {sector} visited {count} times in {len(recent_sectors)} turns",
                ],
                metadata={"sector": sector, "visit_count": count},
            )

    return None


def detect_goal_stagnation(turn_history: list[TurnData], strategy: AIStrategy) -> Anomaly | None:
    """Detect lack of progress toward goal."""
    if len(turn_history) < 15:
        return None

    # Get first and last credit amounts
    first_credits = turn_history[0].credits
    last_credits = turn_history[-1].credits

    # Calculate percent change
    if first_credits == 0:
        return None

    change_pct = abs(last_credits - first_credits) / first_credits

    # Check if change is less than 5%
    if change_pct < 0.05:
        return Anomaly(
            type=AnomalyType.GOAL_STAGNATION,
            priority=InterventionPriority.HIGH,
            confidence=0.75,
            description=f"Credits changed <5% over {len(turn_history)} turns",
            evidence=[
                f"Start credits: {first_credits:,}",
                f"Current credits: {last_credits:,}",
                f"Change: {change_pct:.1%}",
            ],
            metadata={
                "start_credits": first_credits,
                "end_credits": last_credits,
                "change_pct": change_pct,
            },
        )

    return None


def detect_performance_decline(turn_history: list[TurnData]) -> Anomaly | None:
    """Detect declining profit velocity."""
    if len(turn_history) < 10:
        return None

    mid = len(turn_history) // 2

    # Split into first and second half
    first_half = turn_history[:mid]
    second_half = turn_history[mid:]

    # Calculate profit per turn for each half
    first_profit = sum(t.profit_delta for t in first_half) / len(first_half)
    second_profit = sum(t.profit_delta for t in second_half) / len(second_half)

    # Check if second half is >50% worse
    if first_profit > 0 and second_profit < first_profit * 0.5:
        return Anomaly(
            type=AnomalyType.PERFORMANCE_DECLINE,
            priority=InterventionPriority.HIGH,
            confidence=0.7,
            description=f"Profit/turn dropped {(1 - second_profit / first_profit):.0%}",
            evidence=[
                f"First half: {first_profit:.1f} credits/turn",
                f"Second half: {second_profit:.1f} credits/turn",
                f"Decline: {(1 - second_profit / first_profit):.0%}",
            ],
            metadata={
                "first_profit_per_turn": first_profit,
                "second_profit_per_turn": second_profit,
            },
        )

    return None


def detect_turn_waste(turn_history: list[TurnData]) -> Anomaly | None:
    """Detect excessive unproductive turns."""
    if len(turn_history) < 5:
        return None

    # Count turns with zero or negative profit
    wasted = sum(1 for t in turn_history if t.profit_delta <= 0)
    waste_pct = wasted / len(turn_history)

    # Check if >30% wasted
    if waste_pct > 0.3:
        return Anomaly(
            type=AnomalyType.TURN_WASTE,
            priority=InterventionPriority.MEDIUM,
            confidence=0.65,
            description=f"{waste_pct:.0%} of recent turns unproductive",
            evidence=[
                f"{wasted}/{len(turn_history)} turns with ≤0 profit",
                f"Waste rate: {waste_pct:.0%}",
            ],
            metadata={"wasted_turns": wasted, "total_turns": len(turn_history)},
        )

    return None
