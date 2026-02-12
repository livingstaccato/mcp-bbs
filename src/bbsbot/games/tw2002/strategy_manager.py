# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Strategy rotation manager for adaptive strategy switching.

Automatically switches between strategies when one consistently fails.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.bot import TradingBot
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import SectorKnowledge
    from bbsbot.games.tw2002.strategies.base import TradeResult, TradingStrategy

logger = get_logger(__name__)


class StrategyManager:
    """Manages strategy rotation based on performance.

    Features:
    - Tracks consecutive failures per strategy
    - Auto-rotates to next strategy after threshold
    - Prevents rapid cycling with cooldown period
    - Supports configurable rotation order
    """

    def __init__(self, config: BotConfig, knowledge: SectorKnowledge):
        """Initialize strategy manager.

        Args:
            config: Bot configuration
            knowledge: Sector knowledge
        """
        self.config = config
        self.knowledge = knowledge
        self.trading_config = config.trading

        # Current strategy tracking
        self._current_strategy_name: str = config.trading.strategy
        self._current_strategy: TradingStrategy | None = None

        # Failure tracking
        self._consecutive_failures: int = 0
        self._turns_on_current_strategy: int = 0
        self._total_turns: int = 0

        # Rotation history
        self._rotation_history: list[dict] = []

        # Available strategies cache
        self._strategy_cache: dict[str, TradingStrategy] = {}

    def get_current_strategy(self, bot: TradingBot) -> TradingStrategy:
        """Get the currently active strategy.

        Creates strategy instance if needed, handles rotation if enabled.

        Args:
            bot: TradingBot instance

        Returns:
            Active TradingStrategy instance
        """
        # Create strategy if not cached
        if self._current_strategy is None:
            self._current_strategy = self._create_strategy(self._current_strategy_name)
            logger.info(
                "strategy_initialized",
                name=self._current_strategy_name,
                rotation_enabled=self.trading_config.enable_strategy_rotation,
            )

        return self._current_strategy

    def record_result(self, result: TradeResult) -> None:
        """Record action result and check if rotation needed.

        Args:
            result: Result from executing an action
        """
        self._turns_on_current_strategy += 1
        self._total_turns += 1

        # Track failures
        if not result.success:
            self._consecutive_failures += 1
        else:
            # Reset on any success
            self._consecutive_failures = 0

        # Check if rotation needed
        if self.trading_config.enable_strategy_rotation:
            self._maybe_rotate()

    def _maybe_rotate(self) -> None:
        """Check if strategy rotation is needed and execute if so."""
        # Need cooldown period before considering rotation
        if self._turns_on_current_strategy < self.trading_config.rotation_cooldown_turns:
            return

        # Check if failure threshold exceeded
        if self._consecutive_failures < self.trading_config.rotation_failure_threshold:
            return

        # Rotate to next strategy
        self._rotate_strategy()

    def _rotate_strategy(self) -> None:
        """Rotate to the next strategy in the rotation order."""
        rotation_order = self.trading_config.rotation_order

        # Find current position in rotation
        try:
            current_idx = rotation_order.index(self._current_strategy_name)
        except ValueError:
            # Current strategy not in rotation order, start from beginning
            current_idx = -1

        # Get next strategy (wrap around to start)
        next_idx = (current_idx + 1) % len(rotation_order)
        next_strategy_name = rotation_order[next_idx]

        logger.warning(
            "strategy_rotation",
            from_strategy=self._current_strategy_name,
            to_strategy=next_strategy_name,
            consecutive_failures=self._consecutive_failures,
            turns_on_strategy=self._turns_on_current_strategy,
        )

        # Record rotation
        self._rotation_history.append(
            {
                "turn": self._total_turns,
                "from": self._current_strategy_name,
                "to": next_strategy_name,
                "failures": self._consecutive_failures,
                "turns": self._turns_on_current_strategy,
            }
        )

        # Switch to new strategy
        self._current_strategy_name = next_strategy_name
        self._current_strategy = self._create_strategy(next_strategy_name)

        # Reset counters
        self._consecutive_failures = 0
        self._turns_on_current_strategy = 0

    def _create_strategy(self, strategy_name: str) -> TradingStrategy:
        """Create strategy instance by name.

        Args:
            strategy_name: Strategy identifier

        Returns:
            TradingStrategy instance
        """
        # Check cache first
        if strategy_name in self._strategy_cache:
            return self._strategy_cache[strategy_name]

        # Import and create strategy
        from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
        from bbsbot.games.tw2002.strategies.opportunistic import OpportunisticStrategy
        from bbsbot.games.tw2002.strategies.profitable_pairs import ProfitablePairsStrategy
        from bbsbot.games.tw2002.strategies.twerk_optimized import TwerkOptimizedStrategy

        strategy_classes = {
            "ai_strategy": AIStrategy,
            "opportunistic": OpportunisticStrategy,
            "profitable_pairs": ProfitablePairsStrategy,
            "twerk_optimized": TwerkOptimizedStrategy,
        }

        strategy_class = strategy_classes.get(strategy_name)
        if not strategy_class:
            logger.error("unknown_strategy", name=strategy_name)
            # Fallback to opportunistic
            strategy_class = OpportunisticStrategy

        strategy = strategy_class(self.config, self.knowledge)

        # Cache it
        self._strategy_cache[strategy_name] = strategy

        return strategy

    def get_stats(self) -> dict:
        """Get rotation statistics.

        Returns:
            Dictionary with rotation stats
        """
        return {
            "current_strategy": self._current_strategy_name,
            "total_turns": self._total_turns,
            "turns_on_current": self._turns_on_current_strategy,
            "consecutive_failures": self._consecutive_failures,
            "total_rotations": len(self._rotation_history),
            "rotation_history": self._rotation_history,
        }
