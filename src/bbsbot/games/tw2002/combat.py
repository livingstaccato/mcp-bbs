"""Combat avoidance system for TW2002 bot.

Tracks dangerous sectors and provides retreat logic.
"""

from __future__ import annotations

import logging
from time import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
if TYPE_CHECKING:
    from bbsbot.games.tw2002.bot import TradingBot
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge

logger = logging.getLogger(__name__)


class DangerZone(BaseModel):
    """Information about a dangerous sector."""

    sector: int
    threat_level: int  # Number of hostile fighters or danger score
    last_seen: float
    enemy_name: str | None = None
    enemy_type: str | None = None  # "fighter", "trader", "alien"
    notes: str = ""

    model_config = ConfigDict(extra="ignore")


class CombatResult(BaseModel):
    """Result of a combat-related action."""

    success: bool
    action: str  # "retreat", "avoided", "damaged"
    damage_taken: int = 0
    new_sector: int | None = None
    message: str = ""

    model_config = ConfigDict(extra="ignore")


class CombatManager:
    """Manages combat avoidance and danger tracking.

    Handles:
    - Tracking sectors with hostile activity
    - Retreat logic when threatened
    - Avoiding dangerous sectors during navigation
    - Cooldown periods before revisiting danger zones
    """

    def __init__(
        self,
        config: BotConfig,
        knowledge: SectorKnowledge,
    ):
        """Initialize combat manager.

        Args:
            config: Bot configuration
            knowledge: Sector knowledge for navigation
        """
        self.config = config.combat
        self.knowledge = knowledge
        self._danger_zones: dict[int, DangerZone] = {}
        self._last_combat_sector: int | None = None

    def is_dangerous(self, sector: int) -> bool:
        """Check if a sector is currently dangerous.

        Args:
            sector: Sector to check

        Returns:
            True if sector has recent hostile activity
        """
        if not self.config.enabled:
            return False

        if sector not in self._danger_zones:
            return False

        zone = self._danger_zones[sector]

        # Check cooldown
        cooldown_seconds = self.config.enemy_cooldown_minutes * 60
        elapsed = time() - zone.last_seen

        if elapsed >= cooldown_seconds:
            # Danger expired
            del self._danger_zones[sector]
            return False

        # Check threat threshold
        return zone.threat_level >= self.config.danger_threshold

    def mark_dangerous(
        self,
        sector: int,
        threat_level: int,
        enemy_name: str | None = None,
        enemy_type: str | None = None,
        notes: str = "",
    ) -> None:
        """Mark a sector as dangerous.

        Args:
            sector: Sector with hostile activity
            threat_level: Number of fighters or danger score
            enemy_name: Name of hostile (if known)
            enemy_type: Type of threat
            notes: Additional notes
        """
        self._danger_zones[sector] = DangerZone(
            sector=sector,
            threat_level=threat_level,
            last_seen=time(),
            enemy_name=enemy_name,
            enemy_type=enemy_type,
            notes=notes,
        )
        logger.warning(
            f"Marked sector {sector} as dangerous: "
            f"{threat_level} threat level"
        )

    def clear_danger(self, sector: int) -> None:
        """Clear danger status for a sector.

        Args:
            sector: Sector to clear
        """
        if sector in self._danger_zones:
            del self._danger_zones[sector]
            logger.info(f"Cleared danger status for sector {sector}")

    def should_retreat(self, state: GameState) -> bool:
        """Check if we should retreat from current situation.

        Args:
            state: Current game state

        Returns:
            True if retreat is advisable
        """
        if not self.config.enabled:
            return False

        # Check hostile fighters
        if state.hostile_fighters > self.config.danger_threshold:
            return True

        # Check health (shields as proxy for HP)
        shields = state.shields or 100
        max_shields = 100  # Assumption - would be better from ship stats

        health_percent = (shields / max_shields) * 100
        if health_percent < self.config.retreat_health_percent:
            return True

        return False

    def should_avoid(self, state: GameState, sector: int) -> bool:
        """Check if we should avoid entering a sector.

        Args:
            state: Current game state
            sector: Sector we're considering entering

        Returns:
            True if sector should be avoided
        """
        if not self.config.enabled or not self.config.avoid_hostile_sectors:
            return False

        return self.is_dangerous(sector)

    def find_safe_sector(self, state: GameState) -> int | None:
        """Find a safe sector to retreat to.

        Args:
            state: Current game state

        Returns:
            Safe sector number, or None if none found
        """
        warps = state.warps or []

        # First try: find a sector we know is safe
        for warp in warps:
            if not self.is_dangerous(warp):
                info = self.knowledge.get_sector_info(warp)
                if info:
                    return warp

        # Second try: any non-dangerous sector
        for warp in warps:
            if not self.is_dangerous(warp):
                return warp

        # Last resort: pick first warp (retreat anywhere)
        return warps[0] if warps else None

    def find_safe_path(
        self,
        start: int,
        end: int,
        max_hops: int = 100,
    ) -> list[int] | None:
        """Find a path avoiding dangerous sectors.

        Args:
            start: Starting sector
            end: Destination sector
            max_hops: Maximum path length

        Returns:
            Safe path, or None if no safe path exists
        """
        dangerous = {
            s for s in self._danger_zones
            if self.is_dangerous(s)
        }

        if not dangerous:
            return self.knowledge.find_path(start, end, max_hops)

        # BFS avoiding dangerous sectors
        if start == end:
            return [start]

        visited = {start}
        queue = [(start, [start])]

        while queue:
            current, path = queue.pop(0)

            if len(path) > max_hops:
                continue

            warps = self.knowledge.get_warps(current)
            if warps is None:
                continue

            for next_sector in warps:
                if next_sector == end:
                    return path + [next_sector]

                if next_sector not in visited and next_sector not in dangerous:
                    visited.add(next_sector)
                    queue.append((next_sector, path + [next_sector]))

        # No safe path found - return regular path as fallback
        logger.warning(f"No safe path from {start} to {end}, using regular path")
        return self.knowledge.find_path(start, end, max_hops)

    async def retreat(
        self,
        bot: TradingBot,
        state: GameState,
    ) -> CombatResult:
        """Execute retreat to a safe sector.

        Args:
            bot: TradingBot instance
            state: Current game state

        Returns:
            CombatResult with retreat details
        """
        safe_sector = self.find_safe_sector(state)
        if safe_sector is None:
            return CombatResult(
                success=False,
                action="retreat",
                message="No safe sector found for retreat",
            )

        # Mark current sector as dangerous
        if state.sector:
            self.mark_dangerous(
                state.sector,
                state.hostile_fighters,
                notes="Retreated from here",
            )
            self._last_combat_sector = state.sector

        # Execute retreat (warp to safe sector)
        try:
            from bbsbot.games.tw2002.io import send_input, wait_and_respond

            # If in combat, try retreat command first
            if state.context == "combat":
                await send_input(bot, "R", "single_key")
                input_type, prompt_id, screen, kv_data = await wait_and_respond(
                    bot, timeout_ms=5000
                )

                if "retreat" in screen.lower() or "escaped" in screen.lower():
                    logger.info("Retreat successful")
                    return CombatResult(
                        success=True,
                        action="retreat",
                        new_sector=safe_sector,
                        message="Retreated from combat",
                    )

            # Warp to safe sector
            await send_input(bot, "M", "single_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=5000
            )

            await send_input(bot, str(safe_sector), "multi_key")
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=5000
            )

            # Handle any pause screens
            if "pause" in screen.lower() or "[any key]" in screen.lower():
                await send_input(bot, " ", "single_key")

            logger.info(f"Retreated to sector {safe_sector}")
            return CombatResult(
                success=True,
                action="retreat",
                new_sector=safe_sector,
                message=f"Retreated to sector {safe_sector}",
            )

        except Exception as e:
            logger.error(f"Retreat failed: {e}")
            return CombatResult(
                success=False,
                action="retreat",
                message=str(e),
            )

    def update_from_state(self, state: GameState) -> None:
        """Update danger tracking from game state.

        Call this after each orientation to track hostile activity.

        Args:
            state: Current game state
        """
        if not state.sector:
            return

        # Mark sector dangerous if hostile fighters present
        if state.hostile_fighters > 0:
            self.mark_dangerous(
                state.sector,
                state.hostile_fighters,
                enemy_type="fighter",
            )
        elif state.sector in self._danger_zones:
            # Sector clear now - update last_seen to allow faster cooldown
            pass  # Keep the record for cooldown period

        # Track hostile traders
        for trader in state.traders_present:
            # Would need game data to determine if hostile
            pass

    def get_danger_zones(self) -> list[DangerZone]:
        """Get all currently dangerous sectors.

        Returns:
            List of active danger zones
        """
        return [
            zone for zone in self._danger_zones.values()
            if self.is_dangerous(zone.sector)
        ]

    def get_danger_map(self) -> dict[int, int]:
        """Get map of sector -> threat level for active dangers.

        Returns:
            Dictionary of sector number to threat level
        """
        return {
            zone.sector: zone.threat_level
            for zone in self._danger_zones.values()
            if self.is_dangerous(zone.sector)
        }
