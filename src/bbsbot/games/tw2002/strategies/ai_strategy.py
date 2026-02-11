"""AI-powered trading strategy using LLM for decision-making.

This strategy uses a hybrid approach:
- Primary: LLM makes strategic decisions
- Fallback: OpportunisticStrategy handles failures gracefully
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from typing import TYPE_CHECKING

from bbsbot.games.tw2002.interventions.advisor import InterventionAdvisor
from bbsbot.games.tw2002.interventions.trigger import InterventionTrigger
from bbsbot.games.tw2002.strategies.ai import (
    decision_maker,
    goals,
    orchestration,
    validator,
)
from bbsbot.games.tw2002.strategies.ai.parser import ResponseParser
from bbsbot.games.tw2002.strategies.ai.prompts import PromptBuilder
from bbsbot.games.tw2002.strategies.base import (
    TradeAction,
    TradeOpportunity,
    TradeResult,
    TradingStrategy,
)
from bbsbot.games.tw2002.strategies.opportunistic import OpportunisticStrategy
from bbsbot.llm.manager import LLMManager
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from bbsbot.games.tw2002.config import BotConfig, GoalPhase
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
    from bbsbot.llm.types import ChatMessage
    from bbsbot.logging.session_logger import SessionLogger

logger = get_logger(__name__)


class AIStrategy(TradingStrategy):
    """LLM-powered trading strategy with fallback.

    Decision flow:
    1. Build prompt from game state
    2. Query LLM for decision
    3. Parse and validate response
    4. On failure, fallback to OpportunisticStrategy
    5. Track consecutive failures
    """

    def __init__(self, config: BotConfig, knowledge: SectorKnowledge):
        """Initialize AI strategy.

        Args:
            config: Bot configuration
            knowledge: Sector knowledge
        """
        super().__init__(config, knowledge)
        self._settings = config.trading.ai_strategy

        # LLM components
        self.llm_manager = LLMManager(config.llm)
        self.prompt_builder = PromptBuilder()
        self.parser = ResponseParser()

        # Fallback strategy
        self.fallback = OpportunisticStrategy(config, knowledge)
        self._managed_strategies: dict[str, TradingStrategy] = {"opportunistic": self.fallback}
        # End-state default: AI orchestrates concrete strategies, not direct raw actions.
        self._active_managed_strategy: str = "profitable_pairs"
        self._last_action_strategy: str = "profitable_pairs"
        self.consecutive_failures = 0
        self.fallback_until_turn = 0
        self._current_turn = 0

        # Stuck detection: track recent action names
        self._recent_actions: list[str] = []
        self._stuck_threshold: int = 3

        # Ollama verification: warm up model on first call
        self._ollama_verified: bool = False

        # LLM activity status (for dashboard visibility)
        self._is_thinking: bool = False

        # Conversation history for LLM context across turns
        self._conversation_history: list[ChatMessage] = []
        self._max_history_turns: int = 20
        self._last_reasoning: str = ""

        # Feedback loop
        self._recent_events: deque = deque(maxlen=100)  # Rolling window
        self._last_feedback_turn = 0
        self._session_logger: SessionLogger | None = None
        self._viz_emit_cb: Callable[..., None] | None = None

        # Goals system
        self._current_goal_id: str = self._settings.goals.current
        self._last_goal_evaluation_turn = 0
        self._manual_override_until_turn: int | None = None  # None = no override

        # Goal phase tracking for visualization
        self._goal_phases: list[GoalPhase] = []  # Will hold GoalPhase instances
        self._current_phase: GoalPhase | None = None  # Current active phase
        self._max_turns = config.session.max_turns_per_session

        # Start initial goal phase
        # If "auto", start with "profit" as default until first evaluation
        initial_goal = self._current_goal_id if self._current_goal_id != "auto" else "profit"
        self._start_goal_phase(
            goal_id=initial_goal,
            trigger_type="auto",
            reason="Initial goal on strategy creation",
        )
        self._current_goal_id = initial_goal

        # Intervention system
        self._intervention_trigger = InterventionTrigger(
            enabled=self._settings.intervention.enabled,
            min_priority=self._settings.intervention.min_priority,
            cooldown_turns=self._settings.intervention.cooldown_turns,
            max_interventions_per_session=self._settings.intervention.max_per_session,
            session_logger=self._session_logger,
        )
        self._intervention_advisor = InterventionAdvisor(
            config=config,
            llm_manager=self.llm_manager,
        )

    @property
    def name(self) -> str:
        """Strategy name."""
        return "ai_strategy"

    def get_next_action(self, state: GameState) -> tuple[TradeAction, dict]:
        """Determine next action using LLM or fallback.

        NOTE: This is a synchronous wrapper. When called from async code,
        use _get_next_action_async() directly instead.

        If called from within an async context (e.g., already running event loop),
        this will use the fallback strategy to avoid event loop conflicts.

        Args:
            state: Current game state

        Returns:
            Tuple of (action, parameters)
        """
        # Check if we're already in an async context
        try:
            asyncio.get_running_loop()
            # We're in an async context - use fallback to avoid event loop issues
            logger.warning("ai_strategy_sync_call_in_async_context: using fallback")
            return self.fallback.get_next_action(state)
        except RuntimeError:
            # No event loop running - safe to create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._get_next_action_async(state))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

    async def _get_next_action_async(self, state: GameState) -> tuple[TradeAction, dict]:
        """Async implementation of get_next_action.

        Delegates to orchestration module for the main decision flow.

        Args:
            state: Current game state

        Returns:
            Tuple of (action, parameters)
        """
        return await orchestration.orchestrate_decision(self, state)

    async def _make_llm_decision(
        self,
        state: GameState,
        stuck_action: str | None = None,
    ) -> tuple[TradeAction, dict, dict]:
        """Make decision using LLM.

        Delegates to decision_maker module.

        Args:
            state: Current game state
            stuck_action: If set, the action the LLM keeps repeating

        Returns:
            Tuple of (action, parameters, trace)
        """
        return await decision_maker.make_llm_decision(
            strategy=self,
            llm_manager=self.llm_manager,
            parser=self.parser,
            state=state,
            stuck_action=stuck_action,
        )

    def _validate_decision(
        self,
        action: TradeAction,
        params: dict,
        state: GameState,
    ) -> bool:
        """Validate LLM decision against game state.

        Delegates to validator module.
        """
        return validator.validate_decision(action, params, state, self.config)

    def find_opportunities(self, state: GameState) -> list[TradeOpportunity]:
        """Find trading opportunities.

        Delegates to fallback strategy for now.
        Could be enhanced with LLM-based opportunity discovery.

        Args:
            state: Current game state

        Returns:
            List of opportunities
        """
        return self.fallback.find_opportunities(state)

    @property
    def active_managed_strategy(self) -> str:
        """Current strategy chosen by the LLM orchestrator."""
        return self._active_managed_strategy

    def normalize_strategy_name(self, strategy_name: str | None) -> str | None:
        """Normalize strategy aliases from LLM output."""
        if not strategy_name:
            return None
        normalized = str(strategy_name).strip().lower()
        alias_map = {
            "ai": "ai_direct",
            "ai_direct": "ai_direct",
            "direct": "ai_direct",
            "llm": "ai_direct",
            "self": "ai_direct",
            "profitable_pairs": "profitable_pairs",
            "pairs": "profitable_pairs",
            "opportunistic": "opportunistic",
            "twerk_optimized": "twerk_optimized",
            "twerk": "twerk_optimized",
        }
        return alias_map.get(normalized)

    def resolve_requested_strategy(self, params: dict) -> str:
        """Resolve an LLM-requested strategy (or continue current strategy)."""
        requested = params.get("strategy") or params.get("strategy_id")
        normalized = self.normalize_strategy_name(requested)
        if requested and not normalized:
            raise ValueError(f"Unknown strategy selection: {requested}")
        if normalized == "ai_direct":
            # Treat ai_direct as "continue current managed strategy".
            return self._active_managed_strategy or "profitable_pairs"
        if normalized:
            self._active_managed_strategy = normalized
        return self._active_managed_strategy

    def _get_managed_strategy(self, strategy_name: str) -> TradingStrategy:
        """Get or lazily create a managed concrete strategy."""
        if strategy_name in self._managed_strategies:
            return self._managed_strategies[strategy_name]

        if strategy_name == "profitable_pairs":
            from bbsbot.games.tw2002.strategies.profitable_pairs import ProfitablePairsStrategy

            strategy = ProfitablePairsStrategy(self.config, self.knowledge)
        elif strategy_name == "twerk_optimized":
            from bbsbot.games.tw2002.strategies.twerk_optimized import TwerkOptimizedStrategy

            strategy = TwerkOptimizedStrategy(self.config, self.knowledge)
        elif strategy_name == "opportunistic":
            strategy = self.fallback
        else:
            raise ValueError(f"Unsupported managed strategy: {strategy_name}")

        self._managed_strategies[strategy_name] = strategy
        return strategy

    def run_managed_strategy(
        self,
        strategy_name: str,
        state: GameState,
        *,
        update_active: bool = True,
    ) -> tuple[TradeAction, dict]:
        """Run one turn of a concrete strategy selected by the LLM."""
        normalized = self.normalize_strategy_name(strategy_name)
        if normalized is None:
            raise ValueError(f"Unknown strategy selection: {strategy_name}")
        if normalized == "ai_direct":
            raise ValueError("ai_direct is not a concrete managed strategy")
        if update_active:
            self._active_managed_strategy = normalized

        managed = self._get_managed_strategy(normalized)
        with contextlib.suppress(Exception):
            managed.set_policy(self.policy)
        action, params = managed.get_next_action(state)
        self._last_action_strategy = normalized
        return action, params

    def run_fallback_action(self, state: GameState, reason: str) -> tuple[TradeAction, dict]:
        """Execute fallback behavior without changing active strategy selection."""
        action, params = self.run_managed_strategy("opportunistic", state, update_active=False)
        logger.warning("ai_strategy_fallback_action", reason=reason, action=action.name)
        return action, params

    def record_result(self, result: TradeResult) -> None:
        """Record result in AI strategy and delegated concrete strategy."""
        super().record_result(result)
        strategy_name = self._last_action_strategy
        if strategy_name in ("", "ai_direct"):
            return
        with contextlib.suppress(Exception):
            managed = self._get_managed_strategy(strategy_name)
            managed.record_result(result)

    def set_session_logger(self, logger: SessionLogger) -> None:
        """Set session logger for feedback event logging.

        Args:
            logger: Session logger instance
        """
        self._session_logger = logger

    def set_viz_emitter(self, emit_cb: Callable[..., None] | None) -> None:
        """Set an optional visualization emitter callback.

        The callback is expected to accept (kind: str, text: str, turn: int|None, ...).
        """
        self._viz_emit_cb = emit_cb

    def _emit_viz(self, kind: str, text: str) -> None:
        emit = self._viz_emit_cb
        if emit is None:
            return
        try:
            emit(kind, text, turn=self._current_turn, goal_id=self._current_goal_id)
        except Exception as e:
            logger.debug(f"viz_emit_failed: {e}")

    def _record_event(self, event_type: str, data: dict) -> None:
        """Record event for feedback analysis.

        Args:
            event_type: Type of event (e.g., 'decision', 'trade', 'error')
            data: Event data
        """
        self._recent_events.append(
            {
                "type": event_type,
                "timestamp": time.time(),
                **data,
            }
        )

    def record_action_result(
        self,
        action: TradeAction,
        profit_delta: int,
        state: GameState,
    ) -> None:
        """Record action result for intervention detection.

        Args:
            action: Action that was taken
            profit_delta: Profit change from action
            state: Game state after action
        """
        # Update intervention detector
        self._intervention_trigger.update_detector(
            turn=self._current_turn,
            state=state,
            action=action.name,
            profit_delta=profit_delta,
            strategy=self,
        )

        # Also record for feedback
        self._record_event(
            "result",
            {
                "turn": self._current_turn,
                "action": action.name,
                "profit_delta": profit_delta,
                "credits": state.credits,
            },
        )

    def _get_recent_decisions(self) -> list[dict]:
        """Get recent decisions with reasoning for intervention analysis.

        Returns:
            List of recent decision events
        """
        # Return last N decision events from recent_events
        decisions = [e for e in self._recent_events if e.get("type") == "decision"]
        return list(decisions)[-10:]  # Last 10 decisions

    def _apply_intervention(
        self,
        recommendation: dict,
        state: GameState,
    ) -> tuple[TradeAction, dict] | None:
        """Apply intervention recommendation.

        Args:
            recommendation: LLM intervention recommendation
            state: Current game state

        Returns:
            Tuple of (action, params) if recommendation should be applied,
            None otherwise
        """
        action_type = recommendation.get("suggested_action", {}).get("type", "none")
        severity = recommendation.get("severity", "info")

        match action_type:
            case "change_goal":
                # Change to suggested goal
                params = recommendation.get("suggested_action", {}).get("parameters", {})
                new_goal = params.get("goal", "exploration")  # Default to exploration if stuck
                if new_goal and new_goal != self._current_goal_id:
                    logger.info(
                        "intervention_changing_goal",
                        from_goal=self._current_goal_id,
                        to_goal=new_goal,
                        severity=severity,
                    )
                    self.set_goal(new_goal, trigger_type="manual", state=state)
                return None  # Continue with normal decision making

            case "reset_strategy":
                # Reset fallback counter and try fresh
                logger.info("intervention_reset_strategy", severity=severity)
                self.consecutive_failures = 0
                self.fallback_until_turn = 0
                # Also change to exploration to get unstuck
                self.set_goal("exploration", trigger_type="manual", state=state)
                return None

            case "force_move":
                # Force movement to specific sector
                params = recommendation.get("suggested_action", {}).get("parameters", {})
                target_sector = params.get("target_sector")

                # If no target specified but we're stuck, try to find ANY adjacent sector
                if not target_sector and severity == "critical":
                    # Get warps from current sector
                    warps = getattr(state, "warps", [])
                    if warps:
                        target_sector = warps[0]  # Move to first available warp
                        logger.info(
                            "intervention_force_move_auto",
                            target=target_sector,
                            reason="critical_stagnation",
                        )

                if target_sector:
                    logger.info("intervention_force_move", target=target_sector, severity=severity)
                    return TradeAction.MOVE, {"destination": target_sector}
                return None

            case "explore_random":
                # Explore to break out of stuck state
                logger.info("intervention_explore_random", severity=severity)
                # Change goal to exploration
                self.set_goal("exploration", trigger_type="manual", state=state)
                # Let normal decision logic handle exploration
                return None

            case _:
                # No action or unknown type - continue normally
                return None

    async def rewind_to_turn(
        self,
        target_turn: int,
        reason: str,
        state: GameState | None = None,
    ) -> dict:
        """Rewind to a specific turn, marking current phase as failed.

        This allows the bot to backtrack when it encounters a critical failure
        (e.g., ship destroyed, major loss) and retry from an earlier point.

        Args:
            target_turn: Turn number to rewind to
            reason: Reason for rewinding (e.g., "ship destroyed in combat")
            state: Current game state

        Returns:
            Dictionary with rewind details
        """
        if target_turn >= self._current_turn:
            logger.warning(f"rewind_invalid: target={target_turn} >= current={self._current_turn}")
            return {
                "success": False,
                "error": "Cannot rewind to future or current turn",
            }

        old_turn = self._current_turn

        # Mark current phase as rewound
        if self._current_phase:
            self._current_phase.status = "rewound"
            self._current_phase.end_turn = self._current_turn
            self._current_phase.metrics["rewind_reason"] = reason
            self._current_phase.metrics["rewind_to_turn"] = target_turn

        # Set current turn to target
        self._current_turn = target_turn

        # Start new phase with same goal (retry)
        retry_reason = f"Retry after rewind: {reason}"
        self._start_goal_phase(
            goal_id=self._current_goal_id,
            trigger_type="auto",
            reason=retry_reason,
            state=state,
        )

        logger.info(f"rewind_executed: {old_turn} -> {target_turn}, reason={reason}")

        # Log to event ledger
        if self._session_logger:
            await self._session_logger.log_event(
                "goal.rewound",
                {
                    "from_turn": old_turn,
                    "to_turn": target_turn,
                    "reason": reason,
                    "goal": self._current_goal_id,
                },
            )

        return {
            "success": True,
            "from_turn": old_turn,
            "to_turn": target_turn,
            "reason": reason,
            "goal": self._current_goal_id,
        }

    # =========================================================================
    # Goal Management Wrappers - Delegate to goals module
    # =========================================================================

    def get_current_goal(self) -> str:
        """Get current goal ID."""
        return goals.get_current_goal(self)

    def set_goal(
        self, goal_id: str, duration_turns: int = 0, state: GameState | None = None, trigger_type: str = ""
    ) -> None:
        """Manually set current goal."""
        goals.set_goal(self, goal_id, duration_turns, state)

    def _get_goal_config(self, goal_id: str):
        """Get goal configuration by ID."""
        return goals.get_goal_config(self, goal_id)

    def _start_goal_phase(self, goal_id: str, trigger_type: str, reason: str, state: GameState | None = None) -> None:
        """Start a new goal phase."""
        goals.start_goal_phase(self, goal_id, trigger_type, reason, state)

    async def _select_goal(self, state: GameState) -> str:
        """Auto-select best goal based on game state."""
        return await goals.select_goal(self, state)

    async def cleanup(self) -> None:
        """Cleanup resources."""
        # Close final phase
        if self._current_phase and self._current_phase.status == "active":
            self._current_phase.end_turn = self._current_turn
            self._current_phase.status = "completed"

        await self.llm_manager.close()
