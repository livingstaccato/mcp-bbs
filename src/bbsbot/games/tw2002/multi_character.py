"""Multi-character management for TW2002 bot.

Supports multiple characters with configurable knowledge sharing modes.
"""

from __future__ import annotations

import json
import logging
import os
import time as time_module
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import BotConfig

from bbsbot.games.tw2002.character import CharacterManager, CharacterState
from bbsbot.games.tw2002.name_generator import NameGenerator

logger = logging.getLogger(__name__)

KnowledgeSharingMode = Literal["shared", "independent", "inherit_on_death"]


class CharacterRecord(BaseModel):
    """Record of a character's lifecycle."""

    name: str
    ship_name: str | None = None  # Optional themed ship name
    created_at: float
    died_at: float | None = None
    inherited_from: str | None = None
    inherited_to: str | None = None
    sessions: int = 0
    total_profit: int = 0

    model_config = ConfigDict(extra="ignore")


class MultiCharacterManager:
    """Manages multiple characters with knowledge sharing.

    Sharing modes:
    - shared: All characters share the same sector knowledge
    - independent: Each character has isolated knowledge
    - inherit_on_death: New character inherits from dead one

    Features:
    - Character lifecycle tracking
    - Automatic character rotation
    - Knowledge inheritance on death
    - Session statistics aggregation
    """

    def __init__(
        self,
        config: BotConfig,
        data_dir: Path,
        sharing_mode: KnowledgeSharingMode | None = None,
    ):
        """Initialize multi-character manager.

        Args:
            config: Bot configuration
            data_dir: Directory for character data
            sharing_mode: Override sharing mode from config
        """
        self.config = config.multi_character
        self.character_config = config.character
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sharing_mode = sharing_mode or self.config.knowledge_sharing
        self._character_manager = CharacterManager(data_dir)

        # Track all characters
        self._records: dict[str, CharacterRecord] = {}
        self._active_character: str | None = None
        self._character_count = 0

        # Track characters assigned in this session (prevents reusing same char multiple times)
        self._assigned_this_session: set[str] = set()

        # Shared knowledge (for shared mode)
        self._shared_knowledge_path = self.data_dir / "shared_sectors.json"

        # Initialize name generator
        self.name_generator = NameGenerator(seed=self.character_config.name_seed)

        # Load existing records
        self._load_records()

        # Ensure any on-disk character state files have corresponding records.
        # This keeps record-keeping robust across older data layouts and
        # simplifies callers/tests that expect _records entries for state files.
        self._ensure_records_for_existing_characters()

        # Mark existing names as used to avoid collisions
        for record in self._records.values():
            self.name_generator.mark_used(record.name)
            if record.ship_name:
                self.name_generator.mark_used(record.ship_name)

    def _records_path(self) -> Path:
        """Path to character records file."""
        return self.data_dir / "character_records.json"

    def _load_records(self) -> None:
        """Load character records from disk."""
        path = self._records_path()
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text())
            for name, record_data in data.get("records", {}).items():
                record_data["name"] = name
                self._records[name] = CharacterRecord.model_validate(record_data)
            self._character_count = data.get("total_count", len(self._records))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load character records: {e}")

    def _ensure_records_for_existing_characters(self) -> None:
        """Create minimal records for any characters that exist on disk."""
        changed = False
        for name in self._character_manager.list_characters():
            if name in self._records:
                continue
            state = self._character_manager.load(name)
            created_at = state.last_active or time()
            self._records[name] = CharacterRecord(
                name=name,
                ship_name=getattr(state, "ship_name", None),
                created_at=created_at,
                sessions=getattr(state, "sessions_played", 0),
                total_profit=getattr(state, "total_profit", 0),
            )
            changed = True

        if changed:
            self._character_count = max(self._character_count, len(self._records))
            self._save_records()

    def _save_records(self) -> None:
        """Save character records to disk."""
        path = self._records_path()
        data = {
            "records": {name: r.model_dump(mode="json") for name, r in self._records.items()},
            "total_count": self._character_count,
            "sharing_mode": self.sharing_mode,
        }
        path.write_text(json.dumps(data, indent=2))

    def _lock_path(self, name: str) -> Path:
        """Get path to character's lock file."""
        return self.data_dir / f"{name}.lock"

    def _is_character_locked(self, name: str) -> bool:
        """Check if character is currently in use by another process.

        Lock files older than 2 hours are considered stale and ignored.
        """
        lock_file = self._lock_path(name)
        if not lock_file.exists():
            return False

        # Check if lock is stale (older than 2 hours)
        try:
            lock_age = time_module.time() - lock_file.stat().st_mtime
            if lock_age > 7200:  # 2 hours in seconds
                logger.warning(f"Removing stale lock for {name} (age: {lock_age / 3600:.1f} hours)")
                lock_file.unlink()
                return False
        except Exception as e:
            logger.warning(f"Error checking lock for {name}: {e}")
            return False

        return True

    def _lock_character(self, name: str) -> None:
        """Create lock file for character to prevent other processes from using it."""
        lock_file = self._lock_path(name)
        try:
            lock_file.write_text(f"{os.getpid()}\n{time_module.time()}\n")
            logger.debug(f"Locked character: {name}")
        except Exception as e:
            logger.warning(f"Failed to lock character {name}: {e}")

    def _unlock_character(self, name: str) -> None:
        """Remove lock file for character."""
        lock_file = self._lock_path(name)
        try:
            if lock_file.exists():
                lock_file.unlink()
                logger.debug(f"Unlocked character: {name}")
        except Exception as e:
            logger.warning(f"Failed to unlock character {name}: {e}")

    def generate_character_name(self) -> str:
        """Generate a unique themed character name.

        Returns:
            Unique character name like "QuantumTrader" or "NeuralDataProfit"
            or with number prefix: "1QuantumTrader", "2NeuralDataProfit"
        """
        name = self.name_generator.generate_character_name(
            complexity=self.character_config.name_complexity, number_prefix=self.character_config.number_prefix
        )
        logger.info(f"Generated character name: {name}")
        return name

    def generate_ship_name(self) -> str | None:
        """Generate a unique ship name.

        Returns:
            Themed ship name like "Swift Venture" or None if disabled
        """
        if self.character_config.generate_ship_names:
            ship_name = self.name_generator.generate_ship_name(add_number=self.character_config.ship_names_with_numbers)
            logger.info(f"Generated ship name: {ship_name}")
            return ship_name
        return None

    def create_character(self, name: str | None = None, ship_name: str | None = None) -> CharacterState:
        """Create a new character.

        Args:
            name: Optional name (auto-generated if not provided)
            ship_name: Optional ship name (auto-generated if not provided)

        Returns:
            New CharacterState
        """
        if name is None:
            name = self.generate_character_name()

        if ship_name is None:
            ship_name = self.generate_ship_name()

        # Check max characters limit
        living_characters = [r for r in self._records.values() if r.died_at is None]
        if len(living_characters) >= self.config.max_characters:
            logger.warning(f"Max characters ({self.config.max_characters}) reached, oldest will be retired")

        # Create state with ship name
        state = self._character_manager.load(name)
        state.ship_name = ship_name

        # Create record
        self._records[name] = CharacterRecord(
            name=name,
            ship_name=ship_name,
            created_at=time(),
        )
        self._save_records()

        self._active_character = name

        # Lock character to prevent other processes from using it
        self._lock_character(name)

        # Mark as assigned in this session
        self._assigned_this_session.add(name)

        logger.info(f"Created character: {name} (ship: {ship_name or 'none'})")

        return state

    def load_character(self, name: str) -> CharacterState:
        """Load an existing character.

        Args:
            name: Character name

        Returns:
            CharacterState
        """
        state = self._character_manager.load(name)
        self._active_character = name

        # Lock character to prevent other processes from using it
        self._lock_character(name)

        # Mark as assigned in this session
        self._assigned_this_session.add(name)

        # Update record
        if name in self._records:
            self._records[name].sessions += 1
            self._save_records()

        return state

    def save_character(self, state: CharacterState) -> None:
        """Save character state.

        Args:
            state: CharacterState to save
        """
        self._character_manager.save(state)

        # Update record stats
        if state.name in self._records:
            self._records[state.name].total_profit = state.total_profit
            self._save_records()

    def handle_death(
        self,
        dead_character: CharacterState,
    ) -> CharacterState:
        """Handle character death and create successor.

        Applies knowledge inheritance based on sharing mode.

        Args:
            dead_character: The character that died

        Returns:
            New CharacterState for successor
        """
        name = dead_character.name
        logger.info(f"Character {name} died, handling succession")

        # Update death record
        if name in self._records:
            self._records[name].died_at = time()

        # Save final state
        dead_character.record_death()
        self._character_manager.save(dead_character)

        # Create successor
        new_char = self.create_character()

        # Apply inheritance
        if self.sharing_mode == "inherit_on_death":
            self._inherit_knowledge(dead_character, new_char)
            if name in self._records:
                self._records[name].inherited_to = new_char.name
            self._records[new_char.name].inherited_from = name

        self._save_records()
        logger.info(f"Successor created: {new_char.name}")

        return new_char

    def _inherit_knowledge(
        self,
        from_char: CharacterState,
        to_char: CharacterState,
    ) -> None:
        """Transfer knowledge from dead character to successor.

        Args:
            from_char: Dead character
            to_char: New character
        """
        # Inherit visited sectors
        to_char.visited_sectors = from_char.visited_sectors.copy()

        # Inherit scanned sectors
        to_char.scanned_sectors = from_char.scanned_sectors.copy()

        # Inherit danger zones (they're still dangerous!)
        to_char.danger_zones = from_char.danger_zones.copy()

        # Don't inherit credits, bank balance, ship status
        # Those are lost on death

        logger.info(f"Inherited {len(to_char.visited_sectors)} sectors from {from_char.name} to {to_char.name}")

    def get_knowledge_path(self, character_name: str) -> Path:
        """Get path to knowledge file for a character.

        In shared mode, all characters use the same knowledge file.

        Args:
            character_name: Character name

        Returns:
            Path to knowledge file
        """
        if self.sharing_mode == "shared":
            return self._shared_knowledge_path
        else:
            return self.data_dir / f"{character_name}_sectors.json"

    def list_living_characters(self) -> list[str]:
        """Get names of all living characters.

        Returns:
            List of character names that haven't died
        """
        return [name for name, record in self._records.items() if record.died_at is None]

    def list_all_characters(self) -> list[CharacterRecord]:
        """Get records of all characters (living and dead).

        Returns:
            List of all character records
        """
        return list(self._records.values())

    def get_available_characters(self) -> list[str]:
        """Get list of existing character names that can be reused.

        Scans the data directory for character state files and returns
        names of characters that:
        - Have existing state files on disk
        - Are not marked as dead in records (or have no record yet)
        - Have not been assigned in this session
        - Are not locked by another process

        Returns:
            List of character names sorted by last_active time (oldest first)
        """
        # Get all character state files
        existing_chars = self._character_manager.list_characters()

        # Filter out dead characters, already-assigned characters, and locked characters
        available = []
        for name in existing_chars:
            # Skip if already assigned in this session
            if name in self._assigned_this_session:
                continue
            # If we have a record and it's marked dead, skip it
            if name in self._records and self._records[name].died_at is not None:
                continue
            # Skip if locked by another process
            if self._is_character_locked(name):
                continue
            available.append(name)

        # Sort by last active time (oldest first) to distribute load
        def get_last_active(name: str) -> float:
            """Get last active timestamp for sorting."""
            # Try to load state to get last_active time
            try:
                state_path = self.data_dir / f"{name}_state.json"
                if state_path.exists():
                    data = json.loads(state_path.read_text())
                    return data.get("last_active", 0)
            except Exception:
                pass
            return 0

        available.sort(key=get_last_active)
        return available

    def get_or_create_next_character(self) -> CharacterState:
        """Get next available character or create a new one.

        Prioritizes reusing existing character saves before creating new ones.
        This allows characters to build on previous progress across sessions.

        Returns:
            CharacterState (loaded from existing save or newly created)
        """
        # Check for available existing characters
        available = self.get_available_characters()

        if available:
            # Reuse oldest character (by last_active time)
            name = available[0]
            logger.info(f"Reusing existing character: {name}")
            return self.load_character(name)
        else:
            # No existing characters available, create new one
            logger.info("No existing characters available, creating new character")
            return self.create_character()

    def get_active_character(self) -> str | None:
        """Get the currently active character name.

        Returns:
            Active character name or None
        """
        return self._active_character

    def get_aggregate_stats(self) -> dict:
        """Get aggregated statistics across all characters.

        Returns:
            Dictionary with aggregate stats
        """
        total_profit = sum(r.total_profit for r in self._records.values())
        total_sessions = sum(r.sessions for r in self._records.values())
        total_deaths = sum(1 for r in self._records.values() if r.died_at)
        living = sum(1 for r in self._records.values() if not r.died_at)

        return {
            "total_characters": len(self._records),
            "living_characters": living,
            "total_deaths": total_deaths,
            "total_sessions": total_sessions,
            "total_profit": total_profit,
            "avg_profit_per_character": (total_profit / len(self._records) if self._records else 0),
        }

    def cleanup_old_characters(self, max_dead_to_keep: int = 10) -> int:
        """Remove old dead character records.

        Args:
            max_dead_to_keep: Maximum dead records to retain

        Returns:
            Number of records removed
        """
        dead_chars = [(name, record) for name, record in self._records.items() if record.died_at is not None]

        # Sort by death time (oldest first)
        dead_chars.sort(key=lambda x: x[1].died_at or 0)

        # Remove oldest beyond limit
        to_remove = dead_chars[:-max_dead_to_keep] if len(dead_chars) > max_dead_to_keep else []

        for name, _ in to_remove:
            del self._records[name]
            # Also delete state file
            self._character_manager.delete(name)

        if to_remove:
            self._save_records()
            logger.info(f"Cleaned up {len(to_remove)} old character records")

        return len(to_remove)

    def release_all_locks(self) -> None:
        """Release all character locks held by this manager.

        Should be called when bot session ends to free up characters
        for other processes.
        """
        for name in self._assigned_this_session:
            self._unlock_character(name)
        logger.info(f"Released {len(self._assigned_this_session)} character locks")
