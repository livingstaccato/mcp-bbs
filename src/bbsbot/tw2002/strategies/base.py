"""Base classes for trading strategies.

Defines the abstract interface and common data structures for all trading strategies.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field
if TYPE_CHECKING:
    from bbsbot.tw2002.bot import TradingBot
    from bbsbot.tw2002.config import BotConfig
    from bbsbot.tw2002.orientation import GameState, SectorKnowledge

logger = logging.getLogger(__name__)


class TradeAction(Enum):
    """Actions a trading strategy can recommend."""

    TRADE = auto()  # Execute a trade at current location
    MOVE = auto()  # Move to a different sector
    EXPLORE = auto()  # Explore unknown sectors
    BANK = auto()  # Deposit credits at bank
    UPGRADE = auto()  # Buy ship upgrades
    WAIT = auto()  # Wait/do nothing
    RETREAT = auto()  # Flee from danger
    DONE = auto()  # Strategy complete, no more actions


class TradeOpportunity(BaseModel):
    """Represents a potential trading opportunity."""

    buy_sector: int
    sell_sector: int
    commodity: str  # fuel_ore, organics, equipment
    expected_profit: int
    distance: int  # Hops from current location
    path_to_buy: list[int] = Field(default_factory=list)
    path_to_sell: list[int] = Field(default_factory=list)
    confidence: float = 1.0  # How certain we are about this trade

    model_config = ConfigDict(extra="ignore")

    @property
    def profit_per_turn(self) -> float:
        """Calculate expected profit per turn spent."""
        turns_needed = self.distance * 2 + 2  # Travel + buy/sell
        return self.expected_profit / max(turns_needed, 1)


class TradeResult(BaseModel):
    """Result of executing a trade action."""

    success: bool
    action: TradeAction
    profit: int = 0
    message: str = ""
    new_sector: int | None = None
    turns_used: int = 0
    from_sector: int | None = None  # For tracking failed warps
    to_sector: int | None = None    # For tracking failed warps

    model_config = ConfigDict(extra="ignore")


class TradingStrategy(ABC):
    """Abstract base class for trading strategies.

    Strategies analyze the game state and recommend actions.
    They don't directly execute actions - that's the bot's job.
    """

    def __init__(self, config: BotConfig, knowledge: SectorKnowledge):
        """Initialize the strategy.

        Args:
            config: Bot configuration
            knowledge: Sector knowledge for pathfinding
        """
        self.config = config
        self.knowledge = knowledge
        self._trades_executed = 0
        self._total_profit = 0
        self._turns_used = 0

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this strategy."""
        ...

    @abstractmethod
    def get_next_action(self, state: GameState) -> tuple[TradeAction, dict]:
        """Determine the next action to take.

        Args:
            state: Current game state from orientation

        Returns:
            Tuple of (action, parameters):
            - TradeAction.TRADE: {"opportunity": TradeOpportunity}
            - TradeAction.MOVE: {"target_sector": int, "path": list[int]}
            - TradeAction.EXPLORE: {"direction": int | None}
            - TradeAction.BANK: {}
            - TradeAction.UPGRADE: {"upgrade_type": str}
            - TradeAction.WAIT: {}
            - TradeAction.RETREAT: {"safe_sector": int}
            - TradeAction.DONE: {}
        """
        ...

    @abstractmethod
    def find_opportunities(self, state: GameState) -> list[TradeOpportunity]:
        """Find trading opportunities from current position.

        Args:
            state: Current game state

        Returns:
            List of potential trades, sorted by expected profit
        """
        ...

    def record_result(self, result: TradeResult) -> None:
        """Record the result of an executed action.

        Strategies can use this to adapt their behavior.

        Args:
            result: Result of the last action
        """
        if result.success and result.action == TradeAction.TRADE:
            self._trades_executed += 1
            self._total_profit += result.profit
        self._turns_used += result.turns_used
        logger.debug(
            f"Strategy {self.name}: trade #{self._trades_executed}, "
            f"total profit: {self._total_profit}, turns: {self._turns_used}"
        )

    def should_bank(self, state: GameState) -> bool:
        """Check if we should bank credits.

        Args:
            state: Current game state

        Returns:
            True if banking is advisable
        """
        if not self.config.banking.enabled:
            return False
        credits = state.credits or 0
        return credits >= self.config.banking.deposit_threshold

    def should_upgrade(self, state: GameState) -> tuple[bool, str | None]:
        """Check if we should buy upgrades.

        Only recommends upgrades when we have known state and sufficient credits.

        Args:
            state: Current game state

        Returns:
            Tuple of (should_upgrade, upgrade_type)
        """
        if not self.config.upgrades.enabled:
            return False, None

        # Need credits to upgrade - don't recommend with unknown or zero credits
        credits = state.credits
        if credits is None or credits < 1000:
            return False, None

        # Check holds (only if we actually know current holds)
        if self.config.upgrades.auto_buy_holds and state.holds_total is not None:
            if state.holds_total < self.config.upgrades.max_holds:
                return True, "holds"

        # Check fighters (only if we actually know current fighters)
        if self.config.upgrades.auto_buy_fighters and state.fighters is not None:
            if state.fighters < self.config.upgrades.min_fighters:
                return True, "fighters"

        # Check shields (only if we actually know current shields)
        if self.config.upgrades.auto_buy_shields and state.shields is not None:
            if state.shields < self.config.upgrades.min_shields:
                return True, "shields"

        return False, None

    def should_retreat(self, state: GameState) -> bool:
        """Check if we should retreat from danger.

        Args:
            state: Current game state

        Returns:
            True if retreat is advisable
        """
        if not self.config.combat.enabled:
            return False

        # Check hostile fighters
        if state.hostile_fighters > self.config.combat.danger_threshold:
            return True

        # Check health (shields as proxy)
        shields = state.shields or 100
        max_shields = 100  # Default assumption
        health_percent = (shields / max_shields) * 100
        return health_percent < self.config.combat.retreat_health_percent

    def reset_stats(self) -> None:
        """Reset strategy statistics."""
        self._trades_executed = 0
        self._total_profit = 0
        self._turns_used = 0

    @property
    def stats(self) -> dict:
        """Get current strategy statistics."""
        return {
            "trades_executed": self._trades_executed,
            "total_profit": self._total_profit,
            "turns_used": self._turns_used,
            "profit_per_turn": (
                self._total_profit / self._turns_used if self._turns_used > 0 else 0
            ),
        }
