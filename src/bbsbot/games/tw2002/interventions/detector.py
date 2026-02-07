"""Intervention detector for identifying behavioral anomalies and opportunities.

This module implements detection algorithms that analyze bot behavior patterns
to identify stuck states, performance issues, and missed opportunities.
"""

from __future__ import annotations

from collections import Counter, deque
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.state import GameState
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy

logger = get_logger(__name__)


class InterventionPriority(StrEnum):
    """Priority levels for interventions."""

    CRITICAL = "critical"  # Bot stuck, ship at risk, major capital loss
    HIGH = "high"  # Performance declining, suboptimal patterns
    MEDIUM = "medium"  # Minor inefficiencies, optimization opportunities
    LOW = "low"  # Informational, no immediate action needed


class AnomalyType(StrEnum):
    """Types of behavioral anomalies."""

    ACTION_LOOP = "action_loop"  # Repeating same action
    SECTOR_LOOP = "sector_loop"  # Circling between sectors
    GOAL_STAGNATION = "goal_stagnation"  # No progress toward goal
    PERFORMANCE_DECLINE = "performance_decline"  # Profit velocity dropping
    TURN_WASTE = "turn_waste"  # Unproductive turns


class OpportunityType(StrEnum):
    """Types of missed opportunities."""

    HIGH_VALUE_TRADE = "high_value_trade"  # Profitable trade available
    COMBAT_READY = "combat_ready"  # Ship ready for combat
    BANKING_OPTIMAL = "banking_optimal"  # Should secure credits


class Anomaly(BaseModel):
    """Detected behavioral anomaly."""

    type: AnomalyType
    priority: InterventionPriority
    confidence: float = Field(ge=0.0, le=1.0)
    description: str
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Opportunity(BaseModel):
    """Detected opportunity."""

    type: OpportunityType
    priority: InterventionPriority
    confidence: float = Field(ge=0.0, le=1.0)
    description: str
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TurnData(BaseModel):
    """Data about a single turn."""

    turn: int
    sector: int
    credits: int
    action: str
    profit_delta: int
    holds_free: int
    fighters: int
    shields: int


class InterventionDetector:
    """Detects behavioral anomalies and opportunities in bot gameplay.

    Maintains a rolling window of recent turns and runs detection algorithms
    to identify patterns that warrant LLM intervention.
    """

    def __init__(self, window_turns: int = 10) -> None:
        """Initialize detector.

        Args:
            window_turns: Number of recent turns to track
        """
        self._window_turns = window_turns
        self._turn_history: deque[TurnData] = deque(maxlen=window_turns)
        self._recent_anomalies: list[Anomaly] = []
        self._recent_opportunities: list[Opportunity] = []
        self._last_intervention_turn: int | None = None

    def update(
        self,
        turn: int,
        state: GameState,
        action: str,
        profit_delta: int,
        strategy: AIStrategy,
    ) -> None:
        """Update detector with new turn data.

        Args:
            turn: Current turn number
            state: Current game state
            action: Action taken this turn
            profit_delta: Profit change this turn
            strategy: Current strategy instance
        """
        turn_data = TurnData(
            turn=turn,
            sector=state.current_sector,
            credits=state.credits,
            action=action,
            profit_delta=profit_delta,
            holds_free=state.holds_free,
            fighters=state.fighters,
            shields=state.shields,
        )
        self._turn_history.append(turn_data)

    def detect_anomalies(
        self,
        current_turn: int,
        state: GameState,
        strategy: AIStrategy,
    ) -> list[Anomaly]:
        """Run all anomaly detection algorithms.

        Args:
            current_turn: Current turn number
            state: Current game state
            strategy: Current strategy instance

        Returns:
            List of detected anomalies, sorted by priority then confidence
        """
        if len(self._turn_history) < 3:
            return []  # Need minimum data

        anomalies: list[Anomaly] = []

        # Run detection algorithms
        if loop := self._detect_action_loop():
            anomalies.append(loop)

        if sector_loop := self._detect_sector_loop():
            anomalies.append(sector_loop)

        if stagnation := self._detect_goal_stagnation(strategy):
            anomalies.append(stagnation)

        if decline := self._detect_performance_decline():
            anomalies.append(decline)

        if waste := self._detect_turn_waste():
            anomalies.append(waste)

        # Sort by priority (critical first) then confidence (high first)
        priority_order = {
            InterventionPriority.CRITICAL: 0,
            InterventionPriority.HIGH: 1,
            InterventionPriority.MEDIUM: 2,
            InterventionPriority.LOW: 3,
        }
        anomalies.sort(key=lambda a: (priority_order[a.priority], -a.confidence))

        self._recent_anomalies = anomalies
        return anomalies

    def detect_opportunities(
        self,
        current_turn: int,
        state: GameState,
        strategy: AIStrategy,
    ) -> list[Opportunity]:
        """Run all opportunity detection algorithms.

        Args:
            current_turn: Current turn number
            state: Current game state
            strategy: Current strategy instance

        Returns:
            List of detected opportunities, sorted by priority then confidence
        """
        if len(self._turn_history) < 2:
            return []

        opportunities: list[Opportunity] = []

        # Run detection algorithms
        if trade := self._detect_high_value_trade(state, strategy):
            opportunities.append(trade)

        if combat := self._detect_combat_ready(state, strategy):
            opportunities.append(combat)

        if banking := self._detect_banking_optimal(state):
            opportunities.append(banking)

        # Sort by priority then confidence
        priority_order = {
            InterventionPriority.CRITICAL: 0,
            InterventionPriority.HIGH: 1,
            InterventionPriority.MEDIUM: 2,
            InterventionPriority.LOW: 3,
        }
        opportunities.sort(key=lambda o: (priority_order[o.priority], -o.confidence))

        self._recent_opportunities = opportunities
        return opportunities

    def _detect_action_loop(self) -> Anomaly | None:
        """Detect repeated action patterns."""
        if len(self._turn_history) < 3:
            return None

        recent_actions = [t.action for t in list(self._turn_history)[-5:]]

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

    def _detect_sector_loop(self) -> Anomaly | None:
        """Detect circling between same sectors."""
        if len(self._turn_history) < 4:
            return None

        recent_sectors = [t.sector for t in self._turn_history]
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

    def _detect_goal_stagnation(self, strategy: AIStrategy) -> Anomaly | None:
        """Detect lack of progress toward goal."""
        if len(self._turn_history) < 15:
            return None

        # Get first and last credit amounts
        first_credits = self._turn_history[0].credits
        last_credits = self._turn_history[-1].credits

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
                description=f"Credits changed <5% over {len(self._turn_history)} turns",
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

    def _detect_performance_decline(self) -> Anomaly | None:
        """Detect declining profit velocity."""
        if len(self._turn_history) < 10:
            return None

        history = list(self._turn_history)
        mid = len(history) // 2

        # Split into first and second half
        first_half = history[:mid]
        second_half = history[mid:]

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

    def _detect_turn_waste(self) -> Anomaly | None:
        """Detect excessive unproductive turns."""
        if len(self._turn_history) < 5:
            return None

        # Count turns with zero or negative profit
        wasted = sum(1 for t in self._turn_history if t.profit_delta <= 0)
        waste_pct = wasted / len(self._turn_history)

        # Check if >30% wasted
        if waste_pct > 0.3:
            return Anomaly(
                type=AnomalyType.TURN_WASTE,
                priority=InterventionPriority.MEDIUM,
                confidence=0.65,
                description=f"{waste_pct:.0%} of recent turns unproductive",
                evidence=[
                    f"{wasted}/{len(self._turn_history)} turns with ≤0 profit",
                    f"Waste rate: {waste_pct:.0%}",
                ],
                metadata={"wasted_turns": wasted, "total_turns": len(self._turn_history)},
            )

        return None

    def _detect_high_value_trade(self, state: GameState, strategy: AIStrategy) -> Opportunity | None:
        """Detect high-value trade opportunities."""
        # This would integrate with strategy.find_opportunities()
        # For now, return None as placeholder
        return None

    def _detect_combat_ready(self, state: GameState, strategy: AIStrategy) -> Opportunity | None:
        """Detect combat readiness."""
        # Check if ship is combat-ready but goal is not combat
        if state.fighters >= 50 and state.shields >= 100:
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

    def _detect_banking_optimal(self, state: GameState) -> Opportunity | None:
        """Detect optimal banking moment."""
        # Check if carrying significant credits outside FedSpace
        if state.credits >= 100000:
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

    @property
    def recent_anomalies(self) -> list[Anomaly]:
        """Get most recently detected anomalies."""
        return self._recent_anomalies

    @property
    def recent_opportunities(self) -> list[Opportunity]:
        """Get most recently detected opportunities."""
        return self._recent_opportunities

    @property
    def turn_history(self) -> list[TurnData]:
        """Get recent turn history."""
        return list(self._turn_history)
