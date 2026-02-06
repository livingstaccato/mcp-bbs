"""AI-powered trading strategy using LLM for decision-making.

This strategy uses a hybrid approach:
- Primary: LLM makes strategic decisions
- Fallback: OpportunisticStrategy handles failures gracefully
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING

from bbsbot.games.tw2002.config import BotConfig
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

if TYPE_CHECKING:
    from bbsbot.logging.session_logger import SessionLogger

logger = logging.getLogger(__name__)

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

    @property
    def name(self) -> str:
        """Strategy name."""
        return "ai_strategy"

    def get_next_action(self, state: GameState) -> tuple[TradeAction, dict]:
        """Determine next action using LLM or fallback.

        This is a sync wrapper around the async implementation.

        Args:
            state: Current game state

        Returns:
            Tuple of (action, parameters)
        """
        # Run async implementation in event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._get_next_action_async(state))

    async def _get_next_action_async(self, state: GameState) -> tuple[TradeAction, dict]:
        """Async implementation of get_next_action.

        Args:
            state: Current game state

        Returns:
            Tuple of (action, parameters)
        """
        self._current_turn += 1

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
        # Build prompt
        messages = self.prompt_builder.build(state, self.knowledge, self.stats)

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

        return f"""GAMEPLAY SUMMARY (Turns {start_turn}-{self._current_turn}):

Current Status:
- Location: Sector {state.sector or 'Unknown'}
- Credits: {state.credits:,} if state.credits else 'Unknown'
- Turns Remaining: {state.turns_left or 'Unknown'}
- Ship: {state.holds_free}/{state.holds_total} holds free

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

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self.llm_manager.close()
