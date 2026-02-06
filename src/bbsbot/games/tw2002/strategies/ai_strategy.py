"""AI-powered trading strategy using LLM for decision-making.

This strategy uses a hybrid approach:
- Primary: LLM makes strategic decisions
- Fallback: OpportunisticStrategy handles failures gracefully
"""

from __future__ import annotations

import asyncio
import logging
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
from bbsbot.llm.types import ChatRequest

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self.llm_manager.close()
