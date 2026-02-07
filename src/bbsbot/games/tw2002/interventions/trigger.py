"""Intervention trigger coordination.

This module coordinates detection and decides when to invoke LLM analysis,
enforcing cooldowns, budgets, and priority filtering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bbsbot.games.tw2002.interventions.detector import (
    InterventionDetector,
    InterventionPriority,
)
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.state import GameState
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
    from bbsbot.mcp_bbs.session_logger import SessionLogger

logger = get_logger(__name__)


class InterventionTrigger:
    """Coordinates intervention detection and LLM invocation.

    Manages cooldowns, budgets, and priority filtering to decide when
    to trigger LLM-based intervention analysis.
    """

    def __init__(
        self,
        enabled: bool = True,
        min_priority: str = "medium",
        cooldown_turns: int = 5,
        max_interventions_per_session: int = 20,
        window_turns: int = 10,
        session_logger: SessionLogger | None = None,
    ) -> None:
        """Initialize trigger coordinator.

        Args:
            enabled: Whether intervention system is enabled
            min_priority: Minimum priority level to trigger (low/medium/high/critical)
            cooldown_turns: Minimum turns between interventions
            max_interventions_per_session: Maximum interventions per session
            window_turns: Number of turns to track in detector
            session_logger: Optional session logger for recording interventions
        """
        self.enabled = enabled
        self.min_priority = InterventionPriority(min_priority)
        self.cooldown_turns = cooldown_turns
        self._max_interventions_per_session = max_interventions_per_session
        self._session_logger = session_logger

        self.detector = InterventionDetector(window_turns=window_turns)
        self._interventions_this_session = 0
        self._last_intervention_turn: int | None = None

    def update_detector(
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
        if not self.enabled:
            return

        self.detector.update(
            turn=turn,
            state=state,
            action=action,
            profit_delta=profit_delta,
            strategy=strategy,
        )

    def should_intervene(
        self,
        current_turn: int,
        state: GameState,
        strategy: AIStrategy,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Check if intervention should be triggered.

        Args:
            current_turn: Current turn number
            state: Current game state
            strategy: Current strategy instance

        Returns:
            Tuple of (should_intervene, reason, context)
            - should_intervene: Whether to trigger intervention
            - reason: Human-readable reason for intervention
            - context: Dict with anomalies, opportunities, and metadata
        """
        if not self.enabled:
            return False, "", {}

        # Check budget
        if self._interventions_this_session >= self._max_interventions_per_session:
            logger.debug(
                "Intervention budget exhausted",
                interventions=self._interventions_this_session,
                max_interventions=self._max_interventions_per_session,
            )
            return False, "", {}

        # Check cooldown
        if self._last_intervention_turn is not None:
            turns_since_last = current_turn - self._last_intervention_turn
            if turns_since_last < self.cooldown_turns:
                logger.debug(
                    "Intervention on cooldown",
                    turns_since_last=turns_since_last,
                    cooldown=self.cooldown_turns,
                )
                return False, "", {}

        # Run detection
        anomalies = self.detector.detect_anomalies(
            current_turn=current_turn,
            state=state,
            strategy=strategy,
        )
        opportunities = self.detector.detect_opportunities(
            current_turn=current_turn,
            state=state,
            strategy=strategy,
        )

        # Filter by minimum priority
        priority_order = {
            InterventionPriority.CRITICAL: 0,
            InterventionPriority.HIGH: 1,
            InterventionPriority.MEDIUM: 2,
            InterventionPriority.LOW: 3,
        }
        min_priority_value = priority_order[self.min_priority]

        anomalies = [a for a in anomalies if priority_order[a.priority] <= min_priority_value]
        opportunities = [o for o in opportunities if priority_order[o.priority] <= min_priority_value]

        # Check if we have any triggers
        if not anomalies and not opportunities:
            return False, "", {}

        # Build reason and context
        trigger_items = []
        if anomalies:
            trigger_items.append(f"{len(anomalies)} anomalies")
        if opportunities:
            trigger_items.append(f"{len(opportunities)} opportunities")

        reason = f"Detected {', '.join(trigger_items)}"

        # Get highest priority item for primary reason
        all_items: list[Any] = [*anomalies, *opportunities]
        if all_items:
            highest = min(all_items, key=lambda x: priority_order[x.priority])
            reason = f"{highest.priority.upper()}: {highest.description}"

        context = {
            "anomalies": [a.model_dump() for a in anomalies],
            "opportunities": [o.model_dump() for o in opportunities],
            "turn": current_turn,
            "intervention_number": self._interventions_this_session + 1,
        }

        logger.info(
            "Intervention triggered",
            reason=reason,
            anomaly_count=len(anomalies),
            opportunity_count=len(opportunities),
            turn=current_turn,
        )

        return True, reason, context

    async def log_intervention(
        self,
        turn: int,
        reason: str,
        context: dict[str, Any],
        recommendation: dict[str, Any],
    ) -> None:
        """Log intervention to session.

        Args:
            turn: Turn number when intervention occurred
            reason: Reason for intervention
            context: Detection context
            recommendation: LLM recommendation
        """
        self._interventions_this_session += 1
        self._last_intervention_turn = turn

        if self._session_logger:
            await self._session_logger.log_event(
                event="llm.intervention",
                data={
                    "turn": turn,
                    "intervention_number": self._interventions_this_session,
                    "reason": reason,
                    "context": context,
                    "recommendation": recommendation,
                },
            )

    @property
    def interventions_this_session(self) -> int:
        """Get number of interventions triggered this session."""
        return self._interventions_this_session

    @property
    def budget_remaining(self) -> int:
        """Get remaining intervention budget."""
        return self._max_interventions_per_session - self._interventions_this_session
