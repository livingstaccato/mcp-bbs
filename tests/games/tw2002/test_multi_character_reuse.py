"""Test character file reuse functionality."""

from __future__ import annotations

import json
from time import time
from typing import TYPE_CHECKING

import pytest

from bbsbot.games.tw2002.character import CharacterState
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.multi_character import MultiCharacterManager

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for tests."""
    return tmp_path / "test_characters"


@pytest.fixture
def test_config() -> BotConfig:
    """Create a test configuration."""
    config_dict = {
        "connection": {
            "host": "localhost",
            "port": 2002,
        },
        "character": {
            "password": "test123",
        },
        "multi_character": {
            "enabled": True,
            "max_characters": 10,
            "knowledge_sharing": "independent",
        },
    }
    return BotConfig.model_validate(config_dict)


def test_get_or_create_creates_new_when_none_exist(
    test_config: BotConfig,
    test_data_dir: Path,
) -> None:
    """Test that get_or_create_next_character creates new character when none exist."""
    manager = MultiCharacterManager(
        config=test_config,
        data_dir=test_data_dir,
    )

    # Should create a new character
    char1 = manager.get_or_create_next_character()
    assert char1.name
    assert char1.sessions_played == 0

    # Should create a different new character
    char2 = manager.get_or_create_next_character()
    assert char2.name
    assert char2.name != char1.name
    assert char2.sessions_played == 0


def test_get_or_create_reuses_existing_characters(
    test_config: BotConfig,
    test_data_dir: Path,
) -> None:
    """Test that get_or_create_next_character reuses existing character files."""
    test_data_dir.mkdir(parents=True, exist_ok=True)

    # Create some existing character state files
    char_names = ["TestChar1", "TestChar2", "TestChar3"]
    for i, name in enumerate(char_names):
        state = CharacterState(
            name=name,
            sessions_played=i + 1,
            last_active=time() - (100 * i),  # Different ages
        )
        state_path = test_data_dir / f"{name}_state.json"
        state_path.write_text(json.dumps(state.to_dict(), indent=2))

    # Create manager and get characters
    manager = MultiCharacterManager(
        config=test_config,
        data_dir=test_data_dir,
    )

    # Should reuse existing characters (oldest first by last_active)
    char1 = manager.get_or_create_next_character()
    assert char1.name == "TestChar3"  # Oldest last_active
    assert char1.sessions_played == 3

    char2 = manager.get_or_create_next_character()
    assert char2.name == "TestChar2"  # Second oldest
    assert char2.sessions_played == 2

    char3 = manager.get_or_create_next_character()
    assert char3.name == "TestChar1"  # Newest
    assert char3.sessions_played == 1

    # After exhausting existing characters, should create new one
    char4 = manager.get_or_create_next_character()
    assert char4.name not in char_names
    assert char4.sessions_played == 0


def test_get_available_characters_excludes_dead(
    test_config: BotConfig,
    test_data_dir: Path,
) -> None:
    """Test that dead characters are not included in available characters."""
    test_data_dir.mkdir(parents=True, exist_ok=True)

    # Create character state files
    living_char = CharacterState(name="LivingChar", sessions_played=1)
    dead_char = CharacterState(name="DeadChar", sessions_played=2, deaths=1)

    for char in [living_char, dead_char]:
        state_path = test_data_dir / f"{char.name}_state.json"
        state_path.write_text(json.dumps(char.to_dict(), indent=2))

    # Create manager
    manager = MultiCharacterManager(
        config=test_config,
        data_dir=test_data_dir,
    )

    # Mark one character as dead in records
    manager._records["DeadChar"].died_at = time()
    manager._save_records()

    # Get available characters
    available = manager.get_available_characters()

    # Should only include living character
    assert "LivingChar" in available
    assert "DeadChar" not in available


def test_get_available_characters_sorts_by_last_active(
    test_config: BotConfig,
    test_data_dir: Path,
) -> None:
    """Test that available characters are sorted by last_active (oldest first)."""
    test_data_dir.mkdir(parents=True, exist_ok=True)

    # Create characters with different last_active times
    now = time()
    chars = [
        CharacterState(name="NewestChar", last_active=now),
        CharacterState(name="MiddleChar", last_active=now - 1000),
        CharacterState(name="OldestChar", last_active=now - 2000),
    ]

    for char in chars:
        state_path = test_data_dir / f"{char.name}_state.json"
        state_path.write_text(json.dumps(char.to_dict(), indent=2))

    manager = MultiCharacterManager(
        config=test_config,
        data_dir=test_data_dir,
    )

    available = manager.get_available_characters()

    # Should be sorted oldest first
    assert available == ["OldestChar", "MiddleChar", "NewestChar"]


def test_character_reuse_workflow(
    test_config: BotConfig,
    test_data_dir: Path,
) -> None:
    """Test realistic workflow of creating then reusing characters."""
    # First session: Create 3 characters
    manager1 = MultiCharacterManager(
        config=test_config,
        data_dir=test_data_dir,
    )

    chars_session1 = []
    for _ in range(3):
        char = manager1.get_or_create_next_character()
        char.sessions_played += 1
        manager1.save_character(char)
        chars_session1.append(char.name)

    # All should be new
    assert len(chars_session1) == 3
    assert len(set(chars_session1)) == 3  # All unique

    # End of session cleanup: release locks so another process can reuse characters.
    manager1.release_all_locks()

    # Second session: Should reuse those 3 characters
    manager2 = MultiCharacterManager(
        config=test_config,
        data_dir=test_data_dir,
    )

    chars_session2 = []
    for _ in range(3):
        char = manager2.get_or_create_next_character()
        chars_session2.append(char.name)

    # Should reuse existing characters
    assert set(chars_session2) == set(chars_session1)

    # All should have sessions_played > 0 (indicating they're existing)
    for name in chars_session2:
        state_path = test_data_dir / f"{name}_state.json"
        data = json.loads(state_path.read_text())
        assert data["sessions_played"] > 0


def test_mixed_new_and_existing_characters(
    test_config: BotConfig,
    test_data_dir: Path,
) -> None:
    """Test scenario with mix of existing and new characters needed."""
    test_data_dir.mkdir(parents=True, exist_ok=True)

    # Create 2 existing characters
    existing_names = ["ExistingChar1", "ExistingChar2"]
    for name in existing_names:
        state = CharacterState(name=name, sessions_played=1)
        state_path = test_data_dir / f"{name}_state.json"
        state_path.write_text(json.dumps(state.to_dict(), indent=2))

    manager = MultiCharacterManager(
        config=test_config,
        data_dir=test_data_dir,
    )

    # Request 5 characters (2 existing + 3 new)
    all_chars = []
    for _ in range(5):
        char = manager.get_or_create_next_character()
        all_chars.append(char.name)

    # First 2 should be existing
    assert all_chars[0] in existing_names
    assert all_chars[1] in existing_names

    # Last 3 should be new (not in existing_names)
    for name in all_chars[2:]:
        assert name not in existing_names
