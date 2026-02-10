"""Ship upgrade system for TW2002 bot.

Handles automatic purchase of holds, fighters, shields, and ships.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from bbsbot.games.tw2002.bot import TradingBot
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge

logger = logging.getLogger(__name__)


class UpgradeType(Enum):
    """Types of ship upgrades."""

    HOLDS = auto()
    FIGHTERS = auto()
    SHIELDS = auto()
    SHIP = auto()


class UpgradeResult(BaseModel):
    """Result of an upgrade operation."""

    success: bool
    upgrade_type: UpgradeType | None = None
    quantity: int = 0
    cost: int = 0
    message: str = ""

    model_config = ConfigDict(extra="ignore")


class UpgradeNeeds(BaseModel):
    """What upgrades are needed."""

    needs_holds: bool = False
    needs_fighters: bool = False
    needs_shields: bool = False
    holds_to_buy: int = 0
    fighters_to_buy: int = 0
    shields_to_buy: int = 0

    model_config = ConfigDict(extra="ignore")


# Approximate costs (vary by game configuration)
HOLD_COST = 2000
FIGHTER_COST = 200
SHIELD_COST = 50


class UpgradeManager:
    """Manages automatic ship upgrades.

    Handles:
    - Detecting when upgrades are needed
    - Navigating to upgrade locations
    - Purchasing holds, fighters, shields
    - Ship upgrades (future)
    """

    def __init__(
        self,
        config: BotConfig,
        knowledge: SectorKnowledge,
    ):
        """Initialize upgrade manager.

        Args:
            config: Bot configuration
            knowledge: Sector knowledge for navigation
        """
        self.config = config.upgrades
        self.knowledge = knowledge
        self._stardock_sector: int | None = None

    def check_needs(self, state: GameState) -> UpgradeNeeds:
        """Check what upgrades are needed.

        Args:
            state: Current game state

        Returns:
            UpgradeNeeds indicating what to buy
        """
        needs = UpgradeNeeds()

        if not self.config.enabled:
            return needs

        # Check holds
        if self.config.auto_buy_holds:
            holds = state.holds_total or 0
            if holds < self.config.max_holds:
                needs.needs_holds = True
                needs.holds_to_buy = self.config.max_holds - holds

        # Check fighters
        if self.config.auto_buy_fighters:
            fighters = state.fighters or 0
            if fighters < self.config.min_fighters:
                needs.needs_fighters = True
                needs.fighters_to_buy = self.config.min_fighters - fighters

        # Check shields
        if self.config.auto_buy_shields:
            shields = state.shields or 0
            if shields < self.config.min_shields:
                needs.needs_shields = True
                needs.shields_to_buy = self.config.min_shields - shields

        return needs

    def should_upgrade(self, state: GameState) -> tuple[bool, UpgradeType | None]:
        """Check if we should buy upgrades now.

        Considers:
        - What's needed
        - Current credits
        - Current location (can we buy here?)

        Args:
            state: Current game state

        Returns:
            Tuple of (should_upgrade, upgrade_type)
        """
        if not self.config.enabled:
            return False, None

        needs = self.check_needs(state)
        credits = state.credits or 0

        # Priority: shields > fighters > holds
        # (survival first)

        if needs.needs_shields:
            cost = needs.shields_to_buy * SHIELD_COST
            if credits >= cost:
                return True, UpgradeType.SHIELDS

        if needs.needs_fighters:
            cost = needs.fighters_to_buy * FIGHTER_COST
            if credits >= cost:
                return True, UpgradeType.FIGHTERS

        if needs.needs_holds:
            cost = needs.holds_to_buy * HOLD_COST
            if credits >= cost:
                return True, UpgradeType.HOLDS

        return False, None

    def can_upgrade_here(self, state: GameState) -> bool:
        """Check if current location has upgrade facilities.

        Args:
            state: Current game state

        Returns:
            True if upgrades available at current location
        """
        # Stardock has hardware emporium
        if state.context == "stardock":
            return True

        # Some ports have ship facilities
        # Would need to check port class

        return False

    def find_upgrade_location(self, state: GameState) -> int | None:
        """Find nearest location with upgrade facilities.

        Args:
            state: Current game state

        Returns:
            Sector number with upgrades, or None
        """
        if self._stardock_sector:
            return self._stardock_sector

        # Default Stardock location
        return 1

    def path_to_upgrades(self, state: GameState) -> list[int] | None:
        """Calculate path to upgrade location.

        Args:
            state: Current game state

        Returns:
            Path to upgrade sector, or None if unreachable
        """
        upgrade_sector = self.find_upgrade_location(state)
        if upgrade_sector is None:
            return None

        current = state.sector
        if current is None:
            return None

        if current == upgrade_sector:
            return [current]

        return self.knowledge.find_path(current, upgrade_sector)

    async def buy_holds(
        self,
        bot: TradingBot,
        state: GameState,
        quantity: int,
    ) -> UpgradeResult:
        """Buy cargo holds at Stardock.

        Args:
            bot: TradingBot instance
            state: Current game state
            quantity: Number of holds to buy

        Returns:
            UpgradeResult
        """
        if state.context != "stardock":
            return UpgradeResult(
                success=False,
                message="Must be at Stardock to buy holds",
            )

        credits = state.credits or 0
        cost = quantity * HOLD_COST
        if credits < cost:
            # Buy what we can afford
            quantity = credits // HOLD_COST
            if quantity <= 0:
                return UpgradeResult(
                    success=False,
                    message="Insufficient credits for holds",
                )
            cost = quantity * HOLD_COST

        try:
            from bbsbot.games.tw2002.io import send_input, wait_and_respond

            # Enter hardware emporium (H)
            await send_input(bot, "H", "single_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Buy holds (typically option 1 or H)
            await send_input(bot, "H", "single_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Enter quantity
            await send_input(bot, str(quantity), "multi_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Exit hardware
            await send_input(bot, "Q", "single_key")

            # Check success
            if "purchased" in screen.lower() or "added" in screen.lower():
                logger.info(f"Bought {quantity} holds for {cost:,} credits")
                return UpgradeResult(
                    success=True,
                    upgrade_type=UpgradeType.HOLDS,
                    quantity=quantity,
                    cost=cost,
                    message=f"Bought {quantity} holds",
                )

            return UpgradeResult(
                success=False,
                message="Hold purchase may have failed",
            )

        except Exception as e:
            logger.error(f"Failed to buy holds: {e}")
            return UpgradeResult(
                success=False,
                message=str(e),
            )

    async def buy_fighters(
        self,
        bot: TradingBot,
        state: GameState,
        quantity: int,
    ) -> UpgradeResult:
        """Buy fighters at Stardock.

        Args:
            bot: TradingBot instance
            state: Current game state
            quantity: Number of fighters to buy

        Returns:
            UpgradeResult
        """
        if state.context != "stardock":
            return UpgradeResult(
                success=False,
                message="Must be at Stardock to buy fighters",
            )

        credits = state.credits or 0
        cost = quantity * FIGHTER_COST
        if credits < cost:
            quantity = credits // FIGHTER_COST
            if quantity <= 0:
                return UpgradeResult(
                    success=False,
                    message="Insufficient credits for fighters",
                )
            cost = quantity * FIGHTER_COST

        try:
            from bbsbot.games.tw2002.io import send_input, wait_and_respond

            # Enter hardware emporium (H)
            await send_input(bot, "H", "single_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Buy fighters (F)
            await send_input(bot, "F", "single_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Enter quantity
            await send_input(bot, str(quantity), "multi_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Exit hardware
            await send_input(bot, "Q", "single_key")

            if "purchased" in screen.lower():
                logger.info(f"Bought {quantity} fighters for {cost:,} credits")
                return UpgradeResult(
                    success=True,
                    upgrade_type=UpgradeType.FIGHTERS,
                    quantity=quantity,
                    cost=cost,
                    message=f"Bought {quantity} fighters",
                )

            return UpgradeResult(
                success=False,
                message="Fighter purchase may have failed",
            )

        except Exception as e:
            logger.error(f"Failed to buy fighters: {e}")
            return UpgradeResult(
                success=False,
                message=str(e),
            )

    async def buy_shields(
        self,
        bot: TradingBot,
        state: GameState,
        quantity: int,
    ) -> UpgradeResult:
        """Buy shields at Stardock.

        Args:
            bot: TradingBot instance
            state: Current game state
            quantity: Number of shield points to buy

        Returns:
            UpgradeResult
        """
        if state.context != "stardock":
            return UpgradeResult(
                success=False,
                message="Must be at Stardock to buy shields",
            )

        credits = state.credits or 0
        cost = quantity * SHIELD_COST
        if credits < cost:
            quantity = credits // SHIELD_COST
            if quantity <= 0:
                return UpgradeResult(
                    success=False,
                    message="Insufficient credits for shields",
                )
            cost = quantity * SHIELD_COST

        try:
            from bbsbot.games.tw2002.io import send_input, wait_and_respond

            # Enter hardware emporium (H)
            await send_input(bot, "H", "single_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Buy shields (S)
            await send_input(bot, "S", "single_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Enter quantity
            await send_input(bot, str(quantity), "multi_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

            # Exit hardware
            await send_input(bot, "Q", "single_key")

            if "purchased" in screen.lower():
                logger.info(f"Bought {quantity} shields for {cost:,} credits")
                return UpgradeResult(
                    success=True,
                    upgrade_type=UpgradeType.SHIELDS,
                    quantity=quantity,
                    cost=cost,
                    message=f"Bought {quantity} shields",
                )

            return UpgradeResult(
                success=False,
                message="Shield purchase may have failed",
            )

        except Exception as e:
            logger.error(f"Failed to buy shields: {e}")
            return UpgradeResult(
                success=False,
                message=str(e),
            )

    async def upgrade(
        self,
        bot: TradingBot,
        state: GameState,
        upgrade_type: UpgradeType,
    ) -> UpgradeResult:
        """Perform an upgrade of the specified type.

        Args:
            bot: TradingBot instance
            state: Current game state
            upgrade_type: Type of upgrade to perform

        Returns:
            UpgradeResult
        """
        needs = self.check_needs(state)

        if upgrade_type == UpgradeType.HOLDS:
            return await self.buy_holds(bot, state, needs.holds_to_buy)
        elif upgrade_type == UpgradeType.FIGHTERS:
            return await self.buy_fighters(bot, state, needs.fighters_to_buy)
        elif upgrade_type == UpgradeType.SHIELDS:
            return await self.buy_shields(bot, state, needs.shields_to_buy)
        else:
            return UpgradeResult(
                success=False,
                message=f"Unknown upgrade type: {upgrade_type}",
            )

    def set_stardock_sector(self, sector: int) -> None:
        """Set the known Stardock sector.

        Args:
            sector: Sector number containing Stardock
        """
        self._stardock_sector = sector
