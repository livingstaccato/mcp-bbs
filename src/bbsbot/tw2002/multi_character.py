"""Multi-character management for TW2002 bot.

Supports multiple characters with configurable knowledge sharing modes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field
if TYPE_CHECKING:
    from bbsbot.tw2002.config import BotConfig
    from bbsbot.tw2002.orientation import SectorKnowledge

from bbsbot.tw2002.character import CharacterManager, CharacterState

logger = logging.getLogger(__name__)

KnowledgeSharingMode = Literal["shared", "independent", "inherit_on_death"]


class CharacterRecord(BaseModel):
    """Record of a character's lifecycle."""

    name: str
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
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sharing_mode = sharing_mode or self.config.knowledge_sharing
        self._character_manager = CharacterManager(data_dir)

        # Track all characters
        self._records: dict[str, CharacterRecord] = {}
        self._active_character: str | None = None
        self._character_count = 0

        # Shared knowledge (for shared mode)
        self._shared_knowledge_path = self.data_dir / "shared_sectors.json"

        # Load existing records
        self._load_records()

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

    def _save_records(self) -> None:
        """Save character records to disk."""
        path = self._records_path()
        data = {
            "records": {name: r.model_dump(mode="json") for name, r in self._records.items()},
            "total_count": self._character_count,
            "sharing_mode": self.sharing_mode,
        }
        path.write_text(json.dumps(data, indent=2))

    def generate_character_name(self, prefix: str = "bot") -> str:
        """Generate a unique character name.

        Args:
            prefix: Name prefix from config

        Returns:
            Unique character name
        """
        self._character_count += 1
        name = f"{prefix}{self._character_count:03d}"
        logger.info(f"Generated character name: {name}")
        return name

    def create_character(self, name: str | None = None) -> CharacterState:
        """Create a new character.

        Args:
            name: Optional name (auto-generated if not provided)

        Returns:
            New CharacterState
        """
        if name is None:
            prefix = self.config.name_prefix if hasattr(self.config, 'name_prefix') else "bot"
            name = self.generate_character_name(prefix)

        # Check max characters limit
        living_characters = [
            r for r in self._records.values()
            if r.died_at is None
        ]
        if len(living_characters) >= self.config.max_characters:
            logger.warning(
                f"Max characters ({self.config.max_characters}) reached, "
                "oldest will be retired"
            )

        # Create state
        state = self._character_manager.load(name)

        # Create record
        self._records[name] = CharacterRecord(
            name=name,
            created_at=time(),
        )
        self._save_records()

        self._active_character = name
        logger.info(f"Created character: {name}")

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

        logger.info(
            f"Inherited {len(to_char.visited_sectors)} sectors "
            f"from {from_char.name} to {to_char.name}"
        )

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
        return [
            name for name, record in self._records.items()
            if record.died_at is None
        ]

    def list_all_characters(self) -> list[CharacterRecord]:
        """Get records of all characters (living and dead).

        Returns:
            List of all character records
        """
        return list(self._records.values())

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
            "avg_profit_per_character": (
                total_profit / len(self._records) if self._records else 0
            ),
        }

    def cleanup_old_characters(self, max_dead_to_keep: int = 10) -> int:
        """Remove old dead character records.

        Args:
            max_dead_to_keep: Maximum dead records to retain

        Returns:
            Number of records removed
        """
        dead_chars = [
            (name, record)
            for name, record in self._records.items()
            if record.died_at is not None
        ]

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
