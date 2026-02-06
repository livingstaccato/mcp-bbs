"""Per-character state management for TW2002 bot.

Tracks individual character data including resources, ship status,
and visited sectors. Supports persistence across sessions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_serializer
if TYPE_CHECKING:
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge

logger = logging.getLogger(__name__)


class ShipStatus(BaseModel):
    """Current ship configuration and status."""

    ship_type: str = "Merchant Cruiser"
    holds_total: int = 20
    holds_free: int = 20
    fighters: int = 0
    shields: int = 0


class CharacterState(BaseModel):
    """Complete state for a single character.

    Persisted to {name}_state.json for recovery across sessions.
    """

    # Identity
    name: str
    created_at: float = Field(default_factory=time)
    last_active: float = Field(default_factory=time)

    # Resources
    credits: int = 0
    bank_balance: int = 0
    turns_used: int = 0
    total_turns_played: int = 0

    # Ship
    ship: ShipStatus = Field(default_factory=ShipStatus)

    # Location
    current_sector: int | None = None
    last_known_sector: int | None = None

    # Progress tracking
    experience: int = 0
    alignment: int = 0
    corp_id: int | None = None

    # Trading stats
    trades_completed: int = 0
    total_profit: int = 0
    best_trade_profit: int = 0

    # Session tracking
    deaths: int = 0
    sessions_played: int = 0

    # Knowledge tracking
    visited_sectors: set[int] = Field(default_factory=set)
    scanned_sectors: dict[int, float] = Field(default_factory=dict)  # sector -> timestamp

    # Danger zones (sectors with hostile activity)
    danger_zones: dict[int, float] = Field(default_factory=dict)  # sector -> last_seen

    model_config = ConfigDict(extra="ignore")

    @field_serializer("visited_sectors")
    def _serialize_visited(self, value: set[int]) -> list[int]:
        return sorted(value)

    def update_from_game_state(self, state: GameState) -> None:
        """Update character state from game state snapshot.

        Args:
            state: GameState from orientation
        """
        self.last_active = time()

        if state.credits is not None:
            self.credits = state.credits
        if state.sector is not None:
            self.current_sector = state.sector
            self.last_known_sector = state.sector
            self.visited_sectors.add(state.sector)
        if state.turns_left is not None:
            # Calculate turns used this session
            pass  # Would need initial turns to calculate
        if state.experience is not None:
            self.experience = state.experience
        if state.alignment is not None:
            self.alignment = state.alignment
        if state.corp_id is not None:
            self.corp_id = state.corp_id

        # Update ship status
        if state.ship_type:
            self.ship.ship_type = state.ship_type
        if state.holds_total is not None:
            self.ship.holds_total = state.holds_total
        if state.holds_free is not None:
            self.ship.holds_free = state.holds_free
        if state.fighters is not None:
            self.ship.fighters = state.fighters
        if state.shields is not None:
            self.ship.shields = state.shields

        # Track hostile sectors
        if state.hostile_fighters > 0:
            self.danger_zones[state.sector] = time()

    def record_trade(self, profit: int) -> None:
        """Record a completed trade.

        Args:
            profit: Profit from the trade (can be negative for loss)
        """
        self.trades_completed += 1
        self.total_profit += profit
        if profit > self.best_trade_profit:
            self.best_trade_profit = profit

    def record_death(self) -> None:
        """Record character death."""
        self.deaths += 1
        self.current_sector = None

    def mark_scanned(self, sector: int) -> None:
        """Mark a sector as scanned with D command.

        Args:
            sector: Sector number that was scanned
        """
        self.scanned_sectors[sector] = time()

    def needs_scan(self, sector: int, rescan_hours: float = 0) -> bool:
        """Check if a sector needs to be scanned.

        Args:
            sector: Sector to check
            rescan_hours: Hours after which to rescan (0 = never rescan)

        Returns:
            True if sector should be scanned
        """
        if sector not in self.scanned_sectors:
            return True

        if rescan_hours <= 0:
            return False

        last_scan = self.scanned_sectors[sector]
        hours_since = (time() - last_scan) / 3600
        return hours_since >= rescan_hours

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> CharacterState:
        """Create from dictionary (JSON deserialization).

        Args:
            data: Dictionary from JSON

        Returns:
            CharacterState instance
        """
        return cls.model_validate(data)


class CharacterManager:
    """Manages character state persistence.

    Handles loading, saving, and lifecycle of character state files.
    """

    def __init__(self, data_dir: Path):
        """Initialize manager.

        Args:
            data_dir: Directory for character state files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._characters: dict[str, CharacterState] = {}

    def _state_path(self, name: str) -> Path:
        """Get path to character's state file."""
        return self.data_dir / f"{name}_state.json"

    def load(self, name: str) -> CharacterState:
        """Load or create character state.

        Args:
            name: Character name

        Returns:
            CharacterState (loaded from disk or newly created)
        """
        if name in self._characters:
            return self._characters[name]

        path = self._state_path(name)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                state = CharacterState.from_dict(data)
                logger.info(f"Loaded character state for {name}")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load character {name}: {e}, creating new")
                state = CharacterState(name=name)
        else:
            logger.info(f"Creating new character state for {name}")
            state = CharacterState(name=name)

        self._characters[name] = state
        return state

    def save(self, state: CharacterState) -> None:
        """Save character state to disk.

        Args:
            state: CharacterState to save
        """
        path = self._state_path(state.name)
        path.write_text(json.dumps(state.to_dict(), indent=2))
        logger.debug(f"Saved character state for {state.name}")

    def save_all(self) -> None:
        """Save all loaded character states."""
        for state in self._characters.values():
            self.save(state)

    def list_characters(self) -> list[str]:
        """List all saved character names.

        Returns:
            List of character names with state files
        """
        return [
            p.stem.replace("_state", "")
            for p in self.data_dir.glob("*_state.json")
        ]

    def delete(self, name: str) -> bool:
        """Delete character state file.

        Args:
            name: Character name

        Returns:
            True if deleted, False if not found
        """
        if name in self._characters:
            del self._characters[name]

        path = self._state_path(name)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted character state for {name}")
            return True
        return False


class CharacterKnowledge:
    """Extended sector knowledge with character-specific tracking.

    Wraps SectorKnowledge and adds character-specific features like
    scan tracking and danger zone awareness.
    """

    def __init__(
        self,
        base_knowledge: SectorKnowledge,
        character_state: CharacterState,
        rescan_hours: float = 0,
    ):
        """Initialize character knowledge.

        Args:
            base_knowledge: Underlying SectorKnowledge instance
            character_state: Character state for tracking
            rescan_hours: Hours after which to rescan sectors (0 = never)
        """
        self.base = base_knowledge
        self.character = character_state
        self.rescan_hours = rescan_hours

    def needs_scan(self, sector: int) -> bool:
        """Check if sector needs scanning with D command.

        Args:
            sector: Sector to check

        Returns:
            True if sector should be scanned
        """
        return self.character.needs_scan(sector, self.rescan_hours)

    def mark_scanned(self, sector: int) -> None:
        """Mark sector as scanned.

        Args:
            sector: Sector that was scanned
        """
        self.character.mark_scanned(sector)

    def is_dangerous(self, sector: int, cooldown_minutes: int = 30) -> bool:
        """Check if sector is currently dangerous.

        Args:
            sector: Sector to check
            cooldown_minutes: Minutes before danger expires

        Returns:
            True if sector has recent hostile activity
        """
        if sector not in self.character.danger_zones:
            return False

        last_seen = self.character.danger_zones[sector]
        minutes_since = (time() - last_seen) / 60
        return minutes_since < cooldown_minutes

    def mark_dangerous(self, sector: int) -> None:
        """Mark sector as dangerous.

        Args:
            sector: Sector with hostile activity
        """
        self.character.danger_zones[sector] = time()

    def clear_danger(self, sector: int) -> None:
        """Clear danger status for sector.

        Args:
            sector: Sector to clear
        """
        if sector in self.character.danger_zones:
            del self.character.danger_zones[sector]

    # Delegate to base knowledge
    def get_warps(self, sector: int):
        return self.base.get_warps(sector)

    def get_sector_info(self, sector: int):
        return self.base.get_sector_info(sector)

    def record_observation(self, state):
        self.base.record_observation(state)
        if state.sector:
            self.character.visited_sectors.add(state.sector)

    def find_path(self, start: int, end: int, max_hops: int = 100):
        return self.base.find_path(start, end, max_hops)

    def find_safe_path(
        self,
        start: int,
        end: int,
        max_hops: int = 100,
        cooldown_minutes: int = 30,
    ) -> list[int] | None:
        """Find path avoiding dangerous sectors.

        Args:
            start: Starting sector
            end: Target sector
            max_hops: Maximum path length
            cooldown_minutes: Danger cooldown period

        Returns:
            Path avoiding dangerous sectors, or None if no safe path
        """
        # Get dangerous sectors
        dangerous = {
            s for s in self.character.danger_zones
            if self.is_dangerous(s, cooldown_minutes)
        }

        if not dangerous:
            return self.base.find_path(start, end, max_hops)

        # BFS avoiding dangerous sectors
        if start == end:
            return [start]

        visited = {start}
        queue = [(start, [start])]

        while queue:
            current, path = queue.pop(0)

            if len(path) > max_hops:
                continue

            warps = self.base.get_warps(current)
            if warps is None:
                continue

            for next_sector in warps:
                if next_sector == end:
                    return path + [next_sector]

                if next_sector not in visited and next_sector not in dangerous:
                    visited.add(next_sector)
                    queue.append((next_sector, path + [next_sector]))

        # No safe path - try regular path as fallback
        return self.base.find_path(start, end, max_hops)

    def known_sector_count(self) -> int:
        return self.base.known_sector_count()
