"""Intervention detector for identifying behavioral anomalies and opportunities.

This module implements detection algorithms that analyze bot behavior patterns
to identify stuck states, performance issues, and missed opportunities.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from bbsbot.games.tw2002.interventions.detectors import anomaly_detectors, opportunity_detectors
from bbsbot.games.tw2002.interventions.types import (
    Anomaly,
    InterventionPriority,
    Opportunity,
    TurnData,
)
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.orientation import GameState
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy

logger = get_logger(__name__)


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
            sector=state.sector or 0,
            credits=state.credits or 0,
            action=action,
            profit_delta=profit_delta,
            holds_free=state.holds_free or 0,
            fighters=state.fighters or 0,
            shields=state.shields or 0,
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
        turn_history = list(self._turn_history)

        # Run detection algorithms
        # CRITICAL: Check for complete stagnation first
        if complete_stagnation := anomaly_detectors.detect_complete_stagnation(turn_history):
            anomalies.append(complete_stagnation)

        if loop := anomaly_detectors.detect_action_loop(turn_history):
            anomalies.append(loop)

        if sector_loop := anomaly_detectors.detect_sector_loop(turn_history):
            anomalies.append(sector_loop)

        if stagnation := anomaly_detectors.detect_goal_stagnation(turn_history, strategy):
            anomalies.append(stagnation)

        if decline := anomaly_detectors.detect_performance_decline(turn_history):
            anomalies.append(decline)

        if waste := anomaly_detectors.detect_turn_waste(turn_history):
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
        if trade := opportunity_detectors.detect_high_value_trade(state, strategy):
            opportunities.append(trade)

        if combat := opportunity_detectors.detect_combat_ready(state, strategy):
            opportunities.append(combat)

        if banking := opportunity_detectors.detect_banking_optimal(state):
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
