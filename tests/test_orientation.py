# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the orientation system.

Tests GameState, SectorKnowledge, and context detection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.games.tw2002.orientation import (
    GameState,
    SectorInfo,
    SectorKnowledge,
    detect_context,
    parse_display_screen,
    parse_sector_display,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestGameState:
    """Tests for GameState dataclass."""

    def test_is_safe_sector_command(self) -> None:
        """Test is_safe returns True for sector command."""
        state = GameState(context="sector_command")
        assert state.is_safe() is True

    def test_is_safe_planet_command(self) -> None:
        """Test is_safe returns True for planet command."""
        state = GameState(context="planet_command")
        assert state.is_safe() is True

    def test_is_safe_citadel_command(self) -> None:
        """Test is_safe returns True for citadel command."""
        state = GameState(context="citadel_command")
        assert state.is_safe() is True

    def test_is_safe_port_menu(self) -> None:
        """Test is_safe returns False for port menu."""
        state = GameState(context="port_menu")
        assert state.is_safe() is False

    def test_is_safe_unknown(self) -> None:
        """Test is_safe returns False for unknown context."""
        state = GameState(context="unknown")
        assert state.is_safe() is False

    def test_can_warp_with_warps(self) -> None:
        """Test can_warp returns True when at sector command with warps."""
        state = GameState(context="sector_command", warps=[1, 2, 3])
        assert state.can_warp() is True

    def test_can_warp_no_warps(self) -> None:
        """Test can_warp returns False when no warps available."""
        state = GameState(context="sector_command", warps=[])
        assert state.can_warp() is False

    def test_can_warp_wrong_context(self) -> None:
        """Test can_warp returns False when not at sector command."""
        state = GameState(context="planet_command", warps=[1, 2, 3])
        assert state.can_warp() is False

    def test_summary(self) -> None:
        """Test summary produces readable output."""
        state = GameState(
            context="sector_command",
            sector=123,
            credits=50000,
            turns_left=100,
        )
        summary = state.summary()
        assert "sector_command" in summary
        assert "123" in summary
        assert "50000" in summary


class TestContextDetection:
    """Tests for detect_context function."""

    def test_sector_command(self) -> None:
        """Test detection of sector command prompt."""
        screen = """
Sector  : 1
Warps to Sector(s) : 2 - 3

Command [TL=00:00:00]:[1] (?=Help)?"""
        assert detect_context(screen) == "sector_command"

    def test_planet_command(self) -> None:
        """Test detection of planet command prompt."""
        screen = """
Planet Terra
Population: 1000

Planet Command [?=Help]?"""
        assert detect_context(screen) == "planet_command"

    def test_citadel_command(self) -> None:
        """Test detection of citadel command prompt."""
        screen = """
Underground Citadel

Citadel Command [?=Help]?"""
        assert detect_context(screen) == "citadel_command"

    def test_port_menu(self) -> None:
        """Test detection of port menu."""
        screen = """
Commerce report for Port 1
Trading Fuel Ore
<T>rade, <L>eave

Enter your choice [T] ?"""
        assert detect_context(screen) == "port_menu"

    def test_combat(self) -> None:
        """Test detection of combat."""
        screen = """
Enemy ship attacking!
Your shields: 100
Your fighters: 50

Attack [Y/N]?"""
        assert detect_context(screen) == "combat"

    def test_menu(self) -> None:
        """Test detection of generic menu."""
        screen = """
Main Menu
A) Option A
B) Option B

Selection (? for menu):"""
        assert detect_context(screen) == "menu"

    def test_pause(self) -> None:
        """Test detection of pause screen."""
        screen = """
Welcome to Trade Wars!

[Pause] - [Press Space or Enter to continue]"""
        assert detect_context(screen) == "pause"

    def test_unknown(self) -> None:
        """Test unknown screen returns 'unknown'."""
        screen = "Random text that doesn't match anything"
        assert detect_context(screen) == "unknown"


class TestParseDisplayScreen:
    """Tests for parse_display_screen function."""

    def test_parse_credits(self) -> None:
        """Test parsing credits from display."""
        screen = "Credits          : 1,234,567"
        result = parse_display_screen(screen)
        assert result["credits"] == 1234567

    def test_parse_turns(self) -> None:
        """Test parsing turns left from display."""
        screen = "Turns left       : 500"
        result = parse_display_screen(screen)
        assert result["turns_left"] == 500

    def test_parse_fighters(self) -> None:
        """Test parsing fighters from display."""
        screen = "Fighters         : 100"
        result = parse_display_screen(screen)
        assert result["fighters"] == 100

    def test_parse_shields(self) -> None:
        """Test parsing shields from display."""
        screen = "Shields          : 500"
        result = parse_display_screen(screen)
        assert result["shields"] == 500

    def test_parse_holds(self) -> None:
        """Test parsing holds from display."""
        screen = """Total Holds      : 50
Holds w/Goods    : 10"""
        result = parse_display_screen(screen)
        assert result["holds_total"] == 50
        assert result["holds_free"] == 40

    def test_parse_ship_type(self) -> None:
        """Test parsing ship type from display."""
        screen = "Ship type        : Merchant Cruiser"
        result = parse_display_screen(screen)
        assert result["ship_type"] == "Merchant Cruiser"

    def test_parse_alignment(self) -> None:
        """Test parsing alignment from display."""
        screen = "Alignment        : 500 (Good)"
        result = parse_display_screen(screen)
        assert result["alignment"] == 500

    def test_parse_negative_alignment(self) -> None:
        """Test parsing negative alignment from display."""
        screen = "Alignment        : -500 (Evil)"
        result = parse_display_screen(screen)
        assert result["alignment"] == -500

    def test_parse_experience(self) -> None:
        """Test parsing experience from display."""
        screen = "Experience       : 1,000"
        result = parse_display_screen(screen)
        assert result["experience"] == 1000

    def test_parse_sector(self) -> None:
        """Test parsing current sector from display."""
        screen = "Current Sector   : 123"
        result = parse_display_screen(screen)
        assert result["sector"] == 123


class TestParseSectorDisplay:
    """Tests for parse_sector_display function."""

    def test_parse_sector_from_prompt(self) -> None:
        """Test parsing sector from command prompt."""
        screen = "Command [TL=00:00:00]:[123] (?=Help)?"
        result = parse_sector_display(screen)
        assert result["sector"] == 123

    def test_parse_warps(self) -> None:
        """Test parsing warps from sector display."""
        screen = "Warps to Sector(s) : 1 - 2 - 3 - 4"
        result = parse_sector_display(screen)
        assert result["warps"] == [1, 2, 3, 4]

    def test_parse_warps_with_parens(self) -> None:
        """Test parsing warps with parentheses (unexplored)."""
        screen = "Warps to Sector(s) :  (1) - (2) - 3"
        result = parse_sector_display(screen)
        assert result["warps"] == [1, 2, 3]

    def test_parse_port(self) -> None:
        """Test parsing port from sector display."""
        screen = "Ports   : Trading Port (BBS)"
        result = parse_sector_display(screen)
        assert result["has_port"] is True
        assert result["port_class"] == "BBS"

    def test_parse_no_port(self) -> None:
        """Test parsing when no port."""
        screen = "Ports   : None"
        result = parse_sector_display(screen)
        assert result["has_port"] is False

    def test_parse_planet(self) -> None:
        """Test parsing planet from sector display."""
        screen = "Planets : Terra (Class M)"
        result = parse_sector_display(screen)
        assert result["has_planet"] is True
        assert "Terra" in result["planet_names"]

    def test_parse_hostile_fighters(self) -> None:
        """Test parsing hostile fighters."""
        screen = "Fighters: 1,000 (hostile)"
        result = parse_sector_display(screen)
        assert result["hostile_fighters"] == 1000


class TestSectorKnowledge:
    """Tests for SectorKnowledge class."""

    def test_record_and_retrieve(self) -> None:
        """Test recording and retrieving sector info."""
        knowledge = SectorKnowledge()

        state = GameState(
            context="sector_command",
            sector=1,
            warps=[2, 3, 4],
            has_port=True,
            port_class="BBS",
        )
        knowledge.record_observation(state)

        warps = knowledge.get_warps(1)
        assert warps == [2, 3, 4]

        info = knowledge.get_sector_info(1)
        assert info is not None
        assert info.has_port is True
        assert info.port_class == "BBS"

    def test_get_warps_unknown_sector(self) -> None:
        """Test get_warps returns None for unknown sector."""
        knowledge = SectorKnowledge()
        assert knowledge.get_warps(999) is None

    def test_find_path_simple(self) -> None:
        """Test simple pathfinding."""
        knowledge = SectorKnowledge()

        # Create a simple graph: 1 -> 2 -> 3
        knowledge._sectors[1] = SectorInfo(warps=[2])
        knowledge._sectors[2] = SectorInfo(warps=[1, 3])
        knowledge._sectors[3] = SectorInfo(warps=[2])

        path = knowledge.find_path(1, 3)
        assert path == [1, 2, 3]

    def test_find_path_same_sector(self) -> None:
        """Test pathfinding to same sector."""
        knowledge = SectorKnowledge()
        path = knowledge.find_path(1, 1)
        assert path == [1]

    def test_find_path_no_path(self) -> None:
        """Test pathfinding when no path exists."""
        knowledge = SectorKnowledge()

        # Disconnected sectors
        knowledge._sectors[1] = SectorInfo(warps=[2])
        knowledge._sectors[3] = SectorInfo(warps=[4])

        path = knowledge.find_path(1, 3)
        assert path is None

    def test_cache_persistence(self, tmp_path: Path) -> None:
        """Test that knowledge persists to disk."""
        knowledge_dir = tmp_path / "tw2002" / "localhost_2002"

        # Create and populate knowledge
        knowledge1 = SectorKnowledge(
            knowledge_dir=knowledge_dir,
            character_name="testbot",
        )

        state = GameState(
            context="sector_command",
            sector=42,
            warps=[1, 2, 3],
            has_port=True,
            port_class="SSB",
        )
        knowledge1.record_observation(state)

        # Create new instance - should load from cache
        knowledge2 = SectorKnowledge(
            knowledge_dir=knowledge_dir,
            character_name="testbot",
        )

        assert knowledge2.get_warps(42) == [1, 2, 3]
        info = knowledge2.get_sector_info(42)
        assert info is not None
        assert info.port_class == "SSB"

    def test_known_sector_count(self) -> None:
        """Test counting known sectors."""
        knowledge = SectorKnowledge()

        assert knowledge.known_sector_count() == 0

        knowledge._sectors[1] = SectorInfo(warps=[2])
        knowledge._sectors[2] = SectorInfo(warps=[1])

        assert knowledge.known_sector_count() == 2
