"""Banking system for TW2002 bot.

Handles automatic credit deposits at Stardock and planets.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from bbsbot.games.tw2002.bot import TradingBot
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge

logger = logging.getLogger(__name__)

# Known Stardock sector (typically sector 1 in TW2002)
DEFAULT_STARDOCK_SECTOR = 1


class BankingResult(BaseModel):
    """Result of a banking operation."""

    success: bool
    deposited: int = 0
    new_balance: int = 0
    credits_remaining: int = 0
    message: str = ""

    model_config = ConfigDict(extra="ignore")


class BankingManager:
    """Manages automatic banking operations.

    Handles:
    - Detecting when to bank (threshold reached)
    - Navigating to banking location (Stardock)
    - Executing deposit transactions
    - Tracking bank balance
    """

    def __init__(
        self,
        config: BotConfig,
        knowledge: SectorKnowledge,
    ):
        """Initialize banking manager.

        Args:
            config: Bot configuration
            knowledge: Sector knowledge for navigation
        """
        self.config = config.banking
        self.knowledge = knowledge
        self._bank_balance: int = 0
        self._stardock_sector: int | None = None
        self._last_deposit_sector: int | None = None

    @property
    def bank_balance(self) -> int:
        """Current known bank balance."""
        return self._bank_balance

    def should_bank(self, state: GameState) -> bool:
        """Check if we should deposit credits.

        Args:
            state: Current game state

        Returns:
            True if credits exceed threshold and banking is enabled
        """
        if not self.config.enabled:
            return False

        credits = state.credits or 0
        return credits >= self.config.deposit_threshold

    def calculate_deposit(self, credits: int) -> int:
        """Calculate how much to deposit.

        Keeps configured amount on hand for trading.

        Args:
            credits: Current credit balance

        Returns:
            Amount to deposit
        """
        keep = self.config.keep_on_hand
        if credits <= keep:
            return 0
        return credits - keep

    def find_bank_location(self, state: GameState) -> int | None:
        """Find nearest banking location.

        Banking is available at:
        1. Stardock (primary)
        2. Some planets with citadels

        Args:
            state: Current game state

        Returns:
            Sector number with bank, or None
        """
        current = state.sector
        if current is None:
            return None

        # Check if we're at Stardock
        if state.context == "stardock":
            return current

        # Try to find Stardock
        if self._stardock_sector:
            return self._stardock_sector

        # Default to sector 1 (common Stardock location)
        # Could be enhanced to search knowledge for Stardock
        return DEFAULT_STARDOCK_SECTOR

    def path_to_bank(self, state: GameState) -> list[int] | None:
        """Calculate path to nearest bank.

        Args:
            state: Current game state

        Returns:
            Path to bank sector, or None if unreachable
        """
        bank_sector = self.find_bank_location(state)
        if bank_sector is None:
            return None

        current = state.sector
        if current is None:
            return None

        if current == bank_sector:
            return [current]

        return self.knowledge.find_path(current, bank_sector)

    async def deposit(self, bot: TradingBot, state: GameState) -> BankingResult:
        """Execute a deposit transaction.

        Assumes we're at a location with banking available.

        Args:
            bot: TradingBot instance
            state: Current game state

        Returns:
            BankingResult with transaction details
        """
        credits = state.credits or 0
        amount = self.calculate_deposit(credits)

        if amount <= 0:
            return BankingResult(
                success=False,
                message="Nothing to deposit",
            )

        # Bank interface varies by location
        # At Stardock: typically option 'B' for bank
        # At planet citadel: typically 'T' for treasury

        try:
            if state.context == "stardock":
                result = await self._deposit_stardock(bot, amount)
            elif state.context == "citadel_command":
                result = await self._deposit_citadel(bot, amount)
            else:
                return BankingResult(
                    success=False,
                    message=f"Cannot bank from context: {state.context}",
                )

            if result.success:
                self._bank_balance += result.deposited
                self._last_deposit_sector = state.sector
                logger.info(f"Deposited {result.deposited:,} credits, balance: {self._bank_balance:,}")

            return result

        except Exception as e:
            logger.error(f"Banking failed: {e}")
            return BankingResult(
                success=False,
                message=str(e),
            )

    async def _deposit_stardock(
        self,
        bot: TradingBot,
        amount: int,
    ) -> BankingResult:
        """Deposit at Stardock bank.

        Args:
            bot: TradingBot instance
            amount: Amount to deposit

        Returns:
            BankingResult
        """
        from bbsbot.games.tw2002.io import send_input, wait_and_respond

        # Enter bank (B)
        await send_input(bot, "B", "single_key")
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

        # Check if we're in bank menu
        if "bank" not in screen.lower():
            return BankingResult(
                success=False,
                message="Failed to enter bank",
            )

        # Deposit (D)
        await send_input(bot, "D", "single_key")
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

        # Enter amount
        await send_input(bot, str(amount), "multi_key")
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

        # Check for success
        if "deposited" in screen.lower() or "balance" in screen.lower():
            # Exit bank
            await send_input(bot, "Q", "single_key")
            return BankingResult(
                success=True,
                deposited=amount,
                new_balance=self._bank_balance + amount,
                message="Deposit successful",
            )

        # Exit bank on failure
        await send_input(bot, "Q", "single_key")
        return BankingResult(
            success=False,
            message="Deposit may have failed",
        )

    async def _deposit_citadel(
        self,
        bot: TradingBot,
        amount: int,
    ) -> BankingResult:
        """Deposit at planet citadel treasury.

        Args:
            bot: TradingBot instance
            amount: Amount to deposit

        Returns:
            BankingResult
        """
        from bbsbot.games.tw2002.io import send_input, wait_and_respond

        # Enter treasury (T)
        await send_input(bot, "T", "single_key")
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

        # Deposit (D)
        await send_input(bot, "D", "single_key")
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

        # Enter amount
        await send_input(bot, str(amount), "multi_key")
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

        # Check for success
        if "deposited" in screen.lower():
            # Exit treasury
            await send_input(bot, "Q", "single_key")
            return BankingResult(
                success=True,
                deposited=amount,
                new_balance=self._bank_balance + amount,
                message="Deposit successful",
            )

        # Exit treasury
        await send_input(bot, "Q", "single_key")
        return BankingResult(
            success=False,
            message="Deposit may have failed",
        )

    async def withdraw(
        self,
        bot: TradingBot,
        state: GameState,
        amount: int,
    ) -> BankingResult:
        """Withdraw credits from bank.

        Args:
            bot: TradingBot instance
            state: Current game state
            amount: Amount to withdraw

        Returns:
            BankingResult
        """
        if amount > self._bank_balance:
            return BankingResult(
                success=False,
                message=f"Insufficient balance: {self._bank_balance:,}",
            )

        # Similar flow to deposit but with withdraw command
        # Implementation would mirror deposit methods

        return BankingResult(
            success=False,
            message="Withdraw not yet implemented",
        )

    def update_balance(self, balance: int) -> None:
        """Update known bank balance from game state.

        Args:
            balance: Current bank balance from game
        """
        self._bank_balance = balance

    def set_stardock_sector(self, sector: int) -> None:
        """Set the known Stardock sector.

        Args:
            sector: Sector number containing Stardock
        """
        self._stardock_sector = sector
        logger.info(f"Stardock sector set to {sector}")
