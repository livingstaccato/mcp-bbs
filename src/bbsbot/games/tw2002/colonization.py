"""Planet colonization system for TW2002 bot.

Stub module for future colonization features.
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


class PlanetInfo(BaseModel):
    """Information about a planet."""

    name: str
    sector: int
    planet_class: str | None = None  # M, L, K, O, etc.
    has_citadel: bool = False
    colonists: int = 0
    fuel_ore: int = 0
    organics: int = 0
    equipment: int = 0
    fighters: int = 0

    model_config = ConfigDict(extra="ignore")


class ColonizationResult(BaseModel):
    """Result of a colonization operation."""

    success: bool
    action: str  # "colonize", "build_citadel", "transport"
    planet_name: str | None = None
    message: str = ""

    model_config = ConfigDict(extra="ignore")


class ColonizationManager:
    """Manages planet colonization operations.

    Future features:
    - Finding unclaimed planets
    - Dropping colonists
    - Building citadels
    - Transporting goods to/from planets
    - Planet defense setup
    """

    def __init__(
        self,
        config: BotConfig,
        knowledge: SectorKnowledge,
    ):
        """Initialize colonization manager.

        Args:
            config: Bot configuration
            knowledge: Sector knowledge for navigation
        """
        self.config = config
        self.knowledge = knowledge
        self._known_planets: dict[str, PlanetInfo] = {}

    def find_colonizable_planets(self, state: GameState) -> list[PlanetInfo]:
        """Find planets that can be colonized.

        Args:
            state: Current game state

        Returns:
            List of colonizable planets discovered in current sector
        """
        if not state.has_planet or not state.planet_names or state.sector is None:
            return []

        discovered: list[PlanetInfo] = []
        for name in state.planet_names:
            planet = PlanetInfo(name=name, sector=state.sector)
            self.update_planet_info(planet)
            discovered.append(planet)

        logger.debug("Discovered %d planet(s) in sector %s", len(discovered), state.sector)
        return discovered

    def should_colonize(self, state: GameState) -> bool:
        """Check if we should attempt colonization.

        Args:
            state: Current game state

        Returns:
            False (not implemented)
        """
        return False

    async def colonize(
        self,
        bot: TradingBot,
        state: GameState,
        planet_name: str,
    ) -> ColonizationResult:
        """Colonize a planet.

        Args:
            bot: TradingBot instance
            state: Current game state
            planet_name: Name of planet to colonize

        Returns:
            ColonizationResult (failure - not implemented)
        """
        return ColonizationResult(
            success=False,
            action="colonize",
            planet_name=planet_name,
            message="Colonization not yet implemented",
        )

    def update_planet_info(self, planet: PlanetInfo) -> None:
        """Update known information about a planet.

        Args:
            planet: Planet info to record
        """
        self._known_planets[planet.name] = planet

    def get_planet_info(self, name: str) -> PlanetInfo | None:
        """Get known info about a planet.

        Args:
            name: Planet name

        Returns:
            PlanetInfo if known, None otherwise
        """
        return self._known_planets.get(name)

    def list_known_planets(self) -> list[PlanetInfo]:
        """Get all known planets.

        Returns:
            List of known planets
        """
        return list(self._known_planets.values())
