"""AI-powered trading strategy using LLM for decision-making.

This strategy uses a hybrid approach:
- Primary: LLM makes strategic decisions
- Fallback: OpportunisticStrategy handles failures gracefully
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING

from bbsbot.games.tw2002.config import BotConfig, GoalPhase
from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
from bbsbot.games.tw2002.strategies.base import (
    TradeAction,
    TradeOpportunity,
    TradingStrategy,
)
from bbsbot.games.tw2002.strategies.ai.parser import ResponseParser
from bbsbot.games.tw2002.strategies.ai.prompts import PromptBuilder
from bbsbot.games.tw2002.strategies.opportunistic import OpportunisticStrategy
from bbsbot.llm.exceptions import LLMError
from bbsbot.llm.manager import LLMManager
from bbsbot.llm.types import ChatMessage, ChatRequest, ChatResponse
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.logging.session_logger import SessionLogger

logger = get_logger(__name__)

# Feedback loop prompt template
FEEDBACK_SYSTEM_PROMPT = """You are analyzing Trade Wars 2002 gameplay to identify patterns and suggest improvements.
Focus on: trade efficiency, route optimization, resource management, and strategic decision-making.
Keep your analysis concise (2-3 observations)."""


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
        self.consecutive_failures = 0
        self.fallback_until_turn = 0
        self._current_turn = 0

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

        Args:
            state: Current game state

        Returns:
            Tuple of (action, parameters)
        """
        self._current_turn += 1

        # Re-evaluate goal if needed
        await self._maybe_reevaluate_goal(state)

        # Periodic feedback loop
        if (
            self._settings.feedback_enabled
            and self._current_turn % self._settings.feedback_interval_turns == 0
            and self.consecutive_failures < self._settings.fallback_threshold
        ):
            await self._periodic_feedback(state)

        # Check if in fallback mode
        if self.consecutive_failures >= self._settings.fallback_threshold:
            if self._current_turn < self.fallback_until_turn:
                logger.debug(
                    f"ai_strategy_fallback_active: turn={self._current_turn}, until={self.fallback_until_turn}"
                )
                return self.fallback.get_next_action(state)
            else:
                # Try LLM again after cooldown
                logger.info("ai_strategy_fallback_cooldown_expired")
                self.consecutive_failures = 0

        # Try LLM decision
        try:
            action, params = await self._make_llm_decision(state)

            # Validate decision
            if self._validate_decision(action, params, state):
                self.consecutive_failures = 0
                logger.info(
                    f"ai_strategy_decision: action={action.name}, params={params}"
                )
                # Record event for feedback
                self._record_event("decision", {
                    "turn": self._current_turn,
                    "action": action.name,
                    "params": params,
                    "sector": state.sector,
                    "credits": state.credits,
                })
                return action, params
            else:
                raise ValueError("Invalid LLM decision")

        except Exception as e:
            logger.warning(
                f"ai_strategy_failure: {e}, consecutive={self.consecutive_failures + 1}"
            )
            self.consecutive_failures += 1

            # Enter fallback mode if threshold reached
            if self.consecutive_failures >= self._settings.fallback_threshold:
                self.fallback_until_turn = (
                    self._current_turn + self._settings.fallback_duration_turns
                )
                logger.warning(
                    f"ai_strategy_entering_fallback: until_turn={self.fallback_until_turn}"
                )

            return self.fallback.get_next_action(state)

    async def _make_llm_decision(
        self,
        state: GameState,
    ) -> tuple[TradeAction, dict]:
        """Make decision using LLM.

        Args:
            state: Current game state

        Returns:
            Tuple of (action, parameters)

        Raises:
            LLMError: On LLM errors
            ValueError: On invalid response
        """
        # Build prompt with current goal
        goal_config = self._get_goal_config(self._current_goal_id)
        goal_description = goal_config.description if goal_config else None
        goal_instructions = goal_config.instructions if goal_config else None

        messages = self.prompt_builder.build(
            state,
            self.knowledge,
            self.stats,
            goal_description=goal_description,
            goal_instructions=goal_instructions,
        )

        # Query LLM
        provider = await self.llm_manager.get_provider()
        request = ChatRequest(
            messages=messages,
            model=self.config.llm.ollama.model,  # Use configured model
            temperature=0.7,
            max_tokens=500,
        )

        response = await provider.chat(request)

        # Parse response
        action, params = self.parser.parse(response, state)

        return action, params

    def _validate_decision(
        self,
        action: TradeAction,
        params: dict,
        state: GameState,
    ) -> bool:
        """Validate LLM decision against game state.

        Args:
            action: Proposed action
            params: Action parameters
            state: Current game state

        Returns:
            True if decision is valid
        """
        # MOVE requires valid target
        if action == TradeAction.MOVE:
            target = params.get("target_sector")
            if target is None:
                return False
            # Target should be in warps or known sectors
            if state.warps and target not in state.warps:
                logger.debug("invalid_move_target", target=target, warps=state.warps)
                return False

        # TRADE requires being at a port
        if action == TradeAction.TRADE:
            if not state.has_port:
                logger.debug("trade_without_port")
                return False

        # BANK requires banking enabled
        if action == TradeAction.BANK:
            if not self.config.banking.enabled:
                logger.debug("bank_not_enabled")
                return False

        # UPGRADE requires upgrade type
        if action == TradeAction.UPGRADE:
            upgrade_type = params.get("upgrade_type")
            if upgrade_type not in ("holds", "fighters", "shields"):
                logger.debug("invalid_upgrade_type", upgrade_type=upgrade_type)
                return False

        return True

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
        self._recent_events.append({
            "type": event_type,
            "timestamp": time.time(),
            **data,
        })

    async def _periodic_feedback(self, state: GameState) -> None:
        """Generate periodic gameplay analysis using LLM.

        Args:
            state: Current game state
        """
        # Collect data from last N turns
        lookback = self._settings.feedback_lookback_turns
        start_turn = self._current_turn - lookback
        recent_events = [
            e for e in self._recent_events
            if e.get("turn", 0) >= start_turn
        ]

        # Build analysis prompt
        messages = [
            ChatMessage(role="system", content=FEEDBACK_SYSTEM_PROMPT),
            ChatMessage(role="user", content=self._build_feedback_prompt(
                state, recent_events, start_turn
            ))
        ]

        # Query LLM
        request = ChatRequest(
            messages=messages,
            model=self.config.llm.ollama.model,
            temperature=0.7,
            max_tokens=self._settings.feedback_max_tokens,
        )

        start_time = time.time()
        try:
            response = await self.llm_manager.chat(request)
            duration_ms = (time.time() - start_time) * 1000

            # Log to event ledger
            await self._log_feedback(state, messages, response, duration_ms, recent_events)

            logger.info(f"feedback_generated: turn={self._current_turn}, tokens={response.usage.total_tokens if response.usage else 0}")

        except Exception as e:
            logger.warning(f"feedback_loop_error: {e}")

    def _build_feedback_prompt(
        self,
        state: GameState,
        events: list[dict],
        start_turn: int,
    ) -> str:
        """Build feedback analysis prompt.

        Args:
            state: Current game state
            events: Recent events to analyze
            start_turn: Starting turn number for analysis

        Returns:
            Formatted prompt string
        """
        # Count event types
        decisions = [e for e in events if e.get("type") == "decision"]
        trades = [e for e in events if e.get("type") == "trade"]

        # Calculate profit if we have trade data
        profit = 0
        if trades:
            for trade in trades:
                if trade.get("action") == "sell":
                    profit += trade.get("total", 0)
                elif trade.get("action") == "buy":
                    profit -= trade.get("total", 0)

        # Format values safely
        credits_str = f"{state.credits:,}" if state.credits is not None else "Unknown"
        sector_str = str(state.sector) if state.sector is not None else "Unknown"
        turns_str = str(state.turns_left) if state.turns_left is not None else "Unknown"
        holds_str = f"{state.holds_free}/{state.holds_total}" if state.holds_free is not None else "Unknown"

        return f"""GAMEPLAY SUMMARY (Turns {start_turn}-{self._current_turn}):

Current Status:
- Location: Sector {sector_str}
- Credits: {credits_str}
- Turns Remaining: {turns_str}
- Ship: {holds_str} holds free

Recent Activity:
- Decisions Made: {len(decisions)}
- Trades Executed: {len(trades)}
- Net Profit This Period: {profit:,} credits

Recent Decisions:
{self._format_recent_decisions(decisions[-5:])}

Performance Metrics:
- Profit Per Turn: {profit / len(events) if events else 0:.1f}
- Decisions Per Turn: {len(decisions) / self._settings.feedback_lookback_turns:.2f}

Analyze the recent gameplay. What patterns do you notice? What's working well?
What could be improved? Keep your analysis concise (2-3 observations)."""

    def _format_recent_decisions(self, decisions: list[dict]) -> str:
        """Format recent decisions for prompt.

        Args:
            decisions: List of decision events

        Returns:
            Formatted string
        """
        if not decisions:
            return "  None"

        lines = []
        for d in decisions:
            action = d.get("action", "unknown")
            sector = d.get("sector", "?")
            turn = d.get("turn", "?")
            lines.append(f"  Turn {turn}: {action} at sector {sector}")

        return "\n".join(lines)

    async def _log_feedback(
        self,
        state: GameState,
        messages: list[ChatMessage],
        response: ChatResponse,
        duration_ms: float,
        events: list[dict],
    ) -> None:
        """Log feedback to event ledger.

        Args:
            state: Current game state
            messages: Chat messages sent
            response: LLM response
            duration_ms: Response time in milliseconds
            events: Events analyzed
        """
        if not self._session_logger:
            logger.warning("feedback_no_logger: Cannot log feedback without session logger")
            return

        event_data = {
            "turn": self._current_turn,
            "turn_range": [
                self._current_turn - self._settings.feedback_lookback_turns,
                self._current_turn,
            ],
            "prompt": messages[1].content if len(messages) > 1 else "",
            "response": response.message.content,
            "context": {
                "sector": state.sector,
                "credits": state.credits,
                "trades_this_period": len([e for e in events if e.get("type") == "trade"]),
            },
            "metadata": {
                "model": self.config.llm.ollama.model,
                "tokens": {
                    "prompt": response.usage.prompt_tokens if response.usage else 0,
                    "completion": response.usage.completion_tokens if response.usage else 0,
                    "total": response.usage.total_tokens if response.usage else 0,
                },
                "cached": response.cached if hasattr(response, "cached") else False,
                "duration_ms": duration_ms,
            },
        }

        await self._session_logger.log_event("llm.feedback", event_data)

    # -------------------------------------------------------------------------
    # Goals System
    # -------------------------------------------------------------------------

    def get_current_goal(self) -> str:
        """Get current goal ID.

        Returns:
            Goal ID string
        """
        return self._current_goal_id

    def set_goal(self, goal_id: str, duration_turns: int = 0, state: GameState | None = None) -> None:
        """Manually set current goal.

        Args:
            goal_id: Goal ID to activate
            duration_turns: How many turns to maintain (0 = until changed)
            state: Current game state for metrics
        """
        if goal_id not in [g.id for g in self._settings.goals.available]:
            available = [g.id for g in self._settings.goals.available]
            logger.warning(f"goal_not_found: {goal_id}, available: {available}")
            return

        old_goal = self._current_goal_id
        self._current_goal_id = goal_id

        if duration_turns > 0:
            self._manual_override_until_turn = self._current_turn + duration_turns
        else:
            self._manual_override_until_turn = None

        # Start new phase
        reason = f"Manual override for {duration_turns} turns" if duration_turns > 0 else "Manual override"
        self._start_goal_phase(
            goal_id=goal_id,
            trigger_type="manual",
            reason=reason,
            state=state,
        )

        logger.info(f"goal_changed: {old_goal} -> {goal_id}, duration={duration_turns}")

        # Display timeline visualization on manual goal change
        if self._settings.show_goal_visualization:
            from bbsbot.games.tw2002.visualization import GoalTimeline

            timeline = GoalTimeline(
                phases=self._goal_phases,
                current_turn=self._current_turn,
                max_turns=self._max_turns,
            )
            lines: list[str] = []
            lines.append("\n" + "=" * 80)
            lines.append(f"MANUAL GOAL OVERRIDE: {old_goal.upper()} → {goal_id.upper()}")
            if duration_turns > 0:
                lines.append(f"Duration: {duration_turns} turns")
            lines.append("=" * 80)
            lines.append(timeline.render_progress_bar())
            lines.append(timeline.render_legend())
            lines.append("=" * 80 + "\n")
            text = "\n".join(lines)
            print(text)
            self._emit_viz("timeline", text)

        # Log to event ledger
        if self._session_logger:
            import asyncio
            try:
                asyncio.create_task(self._session_logger.log_event("goal.changed", {
                    "turn": self._current_turn,
                    "old_goal": old_goal,
                    "new_goal": goal_id,
                    "duration_turns": duration_turns,
                    "manual_override": True,
                }))
            except Exception as e:
                logger.warning(f"goal_event_logging_failed: {e}")

    def _get_goal_config(self, goal_id: str):
        """Get goal configuration by ID.

        Args:
            goal_id: Goal identifier

        Returns:
            Goal config or None
        """
        for goal in self._settings.goals.available:
            if goal.id == goal_id:
                return goal
        return None

    async def _maybe_reevaluate_goal(self, state: GameState) -> None:
        """Re-evaluate current goal if needed.

        Args:
            state: Current game state
        """
        # Skip if manual override is active
        if self._manual_override_until_turn is not None:
            if self._current_turn < self._manual_override_until_turn:
                return
            else:
                # Override expired
                self._manual_override_until_turn = None
                logger.info("goal_manual_override_expired")

        # Skip if not using auto-select
        if self._settings.goals.current != "auto":
            return

        # Check if it's time to re-evaluate
        turns_since_eval = self._current_turn - self._last_goal_evaluation_turn
        if turns_since_eval < self._settings.goals.reevaluate_every_turns:
            return

        # Re-evaluate and potentially change goal
        new_goal_id = await self._select_goal(state)
        if new_goal_id != self._current_goal_id:
            old_goal = self._current_goal_id
            self._current_goal_id = new_goal_id

            # Determine reason for auto-selection
            goal_config = self._get_goal_config(new_goal_id)
            reason = f"Auto-selected: {goal_config.description if goal_config else 'triggers matched'}"

            # Start new phase
            self._start_goal_phase(
                goal_id=new_goal_id,
                trigger_type="auto",
                reason=reason,
                state=state,
            )

            logger.info(f"goal_auto_changed: {old_goal} -> {new_goal_id}")

            # Display timeline visualization on goal change
            if self._settings.show_goal_visualization:
                from bbsbot.games.tw2002.visualization import GoalTimeline

                timeline = GoalTimeline(
                    phases=self._goal_phases,
                    current_turn=self._current_turn,
                    max_turns=self._max_turns,
                )
                lines: list[str] = []
                lines.append("\n" + "=" * 80)
                lines.append(f"GOAL CHANGED: {old_goal.upper()} → {new_goal_id.upper()}")
                lines.append("=" * 80)
                lines.append(timeline.render_progress_bar())
                lines.append(timeline.render_legend())
                lines.append("=" * 80 + "\n")
                text = "\n".join(lines)
                print(text)
                self._emit_viz("timeline", text)

            # Log to event ledger
            if self._session_logger:
                await self._session_logger.log_event("goal.changed", {
                    "turn": self._current_turn,
                    "old_goal": old_goal,
                    "new_goal": new_goal_id,
                    "duration_turns": 0,
                    "manual_override": False,
                    "auto_selected": True,
                })

        self._last_goal_evaluation_turn = self._current_turn

    async def _select_goal(self, state: GameState) -> str:
        """Auto-select best goal based on game state.

        Args:
            state: Current game state

        Returns:
            Best goal ID
        """
        priority_weights = {"low": 1, "medium": 2, "high": 3}

        # Score each goal
        scored_goals = []
        for goal in self._settings.goals.available:
            score = self._evaluate_goal_triggers(goal, state)
            priority_weight = priority_weights.get(goal.priority, 2)
            final_score = score * priority_weight
            scored_goals.append((goal.id, final_score, goal.priority))

        # Pick highest scoring goal
        if scored_goals:
            best = max(scored_goals, key=lambda x: x[1])
            return best[0]

        # Fallback to profit if no triggers match
        return "profit"

    def _evaluate_goal_triggers(self, goal, state: GameState) -> float:
        """Evaluate how well a goal's triggers match current state.

        Args:
            goal: Goal configuration
            state: Current game state

        Returns:
            Score from 0.0 (no match) to 1.0 (perfect match)
        """
        triggers = goal.trigger_when
        matches = 0
        total_conditions = 0

        # Check credits conditions
        if triggers.credits_below is not None:
            total_conditions += 1
            if state.credits is not None and state.credits < triggers.credits_below:
                matches += 1

        if triggers.credits_above is not None:
            total_conditions += 1
            if state.credits is not None and state.credits > triggers.credits_above:
                matches += 1

        # Check fighters conditions
        if triggers.fighters_below is not None:
            total_conditions += 1
            if state.fighters is not None and state.fighters < triggers.fighters_below:
                matches += 1

        if triggers.fighters_above is not None:
            total_conditions += 1
            if state.fighters is not None and state.fighters > triggers.fighters_above:
                matches += 1

        # Check shields conditions
        if triggers.shields_below is not None:
            total_conditions += 1
            if state.shields is not None and state.shields < triggers.shields_below:
                matches += 1

        if triggers.shields_above is not None:
            total_conditions += 1
            if state.shields is not None and state.shields > triggers.shields_above:
                matches += 1

        # Check turns conditions
        if triggers.turns_remaining_above is not None:
            total_conditions += 1
            if state.turns_left is not None and state.turns_left > triggers.turns_remaining_above:
                matches += 1

        if triggers.turns_remaining_below is not None:
            total_conditions += 1
            if state.turns_left is not None and state.turns_left < triggers.turns_remaining_below:
                matches += 1

        # Check sector knowledge (would need to query self.knowledge)
        if triggers.sectors_known_below is not None:
            total_conditions += 1
            known_count = self.knowledge.known_sector_count() if self.knowledge else 0
            if known_count < triggers.sectors_known_below:
                matches += 1

        # If no conditions specified, give low score
        if total_conditions == 0:
            return 0.1

        # Return match ratio
        return matches / total_conditions

    def _start_goal_phase(
        self,
        goal_id: str,
        trigger_type: str,
        reason: str,
        state: GameState | None = None,
    ) -> None:
        """Start a new goal phase.

        Args:
            goal_id: Goal ID to start
            trigger_type: "auto" or "manual"
            reason: Why this goal was selected
            state: Current game state for metrics
        """
        # Close current phase if active
        if self._current_phase:
            self._current_phase.end_turn = self._current_turn
            self._current_phase.status = "completed"

            # Record end metrics
            if state:
                self._current_phase.metrics["end_credits"] = state.credits
                self._current_phase.metrics["end_fighters"] = state.fighters
                self._current_phase.metrics["end_shields"] = state.shields
                self._current_phase.metrics["end_holds"] = state.holds_total

        # Create new phase
        metrics = {}
        if state:
            metrics = {
                "start_credits": state.credits,
                "start_fighters": state.fighters,
                "start_shields": state.shields,
                "start_holds": state.holds_total,
            }

        self._current_phase = GoalPhase(
            goal_id=goal_id,
            start_turn=self._current_turn,
            end_turn=None,
            status="active",
            trigger_type=trigger_type,
            metrics=metrics,
            reason=reason,
        )
        self._goal_phases.append(self._current_phase)

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
            await self._session_logger.log_event("goal.rewound", {
                "from_turn": old_turn,
                "to_turn": target_turn,
                "reason": reason,
                "goal": self._current_goal_id,
            })

        return {
            "success": True,
            "from_turn": old_turn,
            "to_turn": target_turn,
            "reason": reason,
            "goal": self._current_goal_id,
        }

    async def cleanup(self) -> None:
        """Cleanup resources."""
        # Close final phase
        if self._current_phase and self._current_phase.status == "active":
            self._current_phase.end_turn = self._current_turn
            self._current_phase.status = "completed"

        await self.llm_manager.close()
