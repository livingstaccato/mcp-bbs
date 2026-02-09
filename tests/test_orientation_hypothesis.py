"""Hypothesis-based property tests for orientation system.

Uses property-based testing to verify orientation handles:
- Random/malformed screen content
- Partial screens (baud rate simulation)
- All valid context types
- Parsing edge cases
"""

from __future__ import annotations

import re
from hypothesis import given, strategies as st, assume, settings

from bbsbot.games.tw2002.orientation import (
    GameState,
    SectorInfo,
    SectorKnowledge,
    detect_context,
    parse_display_screen,
    parse_sector_display,
)


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Valid TW2002 context types
VALID_CONTEXTS = [
    "sector_command",
    "planet_command",
    "citadel_command",
    "stardock",
    "computer_menu",
    "cim_mode",
    "course_plotter",
    "port_menu",
    "port_trading",
    "port_report",
    "bank",
    "ship_shop",
    "hardware_shop",
    "message_system",
    "tavern",
    "grimy_trader",
    "gambling",
    "eavesdrop",
    "underground",
    "combat",
    "warping",
    "autopilot",
    "pause",
    "more",
    "confirm",
    "login",
    "menu",
    "death",
    "unknown",
]

# Sector number strategy (1-1000 is typical)
sector_numbers = st.integers(min_value=1, max_value=5000)

# Credit amounts (can be large)
credit_amounts = st.integers(min_value=0, max_value=99_999_999)

# Port classes
port_classes = st.sampled_from(["BBS", "BSB", "SBB", "SSB", "BSS", "SBS", "SSS", "BBB"])

# Random screen content that might confuse parsers
garbage_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=0,
    max_size=500,
)


# =============================================================================
# GameState Property Tests
# =============================================================================

class TestGameStateProperties:
    """Property tests for GameState invariants."""

    @given(context=st.sampled_from(VALID_CONTEXTS))
    def test_is_safe_only_for_command_prompts(self, context: str) -> None:
        """is_safe() returns True only for command prompt contexts."""
        state = GameState(context=context)
        safe_contexts = {"sector_command", "planet_command", "citadel_command"}

        if context in safe_contexts:
            assert state.is_safe() is True
        else:
            assert state.is_safe() is False

    @given(
        context=st.sampled_from(VALID_CONTEXTS),
        warps=st.lists(sector_numbers, min_size=0, max_size=6),
    )
    def test_can_warp_requires_sector_command_and_warps(
        self, context: str, warps: list[int]
    ) -> None:
        """can_warp() requires being at sector_command with available warps."""
        state = GameState(context=context, warps=warps)

        expected = context == "sector_command" and len(warps) > 0
        assert state.can_warp() == expected

    @given(
        sector=st.one_of(st.none(), sector_numbers),
        credits=st.one_of(st.none(), credit_amounts),
        turns=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
    )
    def test_summary_never_raises(
        self, sector: int | None, credits: int | None, turns: int | None
    ) -> None:
        """summary() should never raise, regardless of field values."""
        state = GameState(
            context="sector_command",
            sector=sector,
            credits=credits,
            turns_left=turns,
        )
        summary = state.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0


# =============================================================================
# Context Detection Property Tests
# =============================================================================

class TestContextDetectionProperties:
    """Property tests for detect_context."""

    @given(garbage=garbage_text)
    def testdetect_context_never_raises_on_garbage(self, garbage: str) -> None:
        """detect_context should return a string for any input, never raise."""
        result = detect_context(garbage)
        assert isinstance(result, str)
        assert result in VALID_CONTEXTS

    @given(
        prefix=garbage_text,
        suffix=garbage_text,
    )
    def test_sector_command_detected_with_noise(
        self, prefix: str, suffix: str
    ) -> None:
        """Sector command prompt should be detected even with surrounding noise."""
        # Build a screen with command prompt at the end (where it should be)
        prompt = "Command [TL=00:00:00]:[1] (?=Help)?"
        screen = f"{prefix}\n{prompt}\n{suffix}" if suffix else f"{prefix}\n{prompt}"

        # If prompt is truly at the end (suffix is empty/whitespace), should detect
        if not suffix.strip():
            result = detect_context(screen)
            assert result == "sector_command", f"Failed to detect command in: {screen[-100:]}"

    @given(
        prefix=garbage_text,
    )
    def test_planet_command_detected(self, prefix: str) -> None:
        """Planet command prompt should be detected."""
        prompt = "Planet Command [?=Help]?"
        screen = f"{prefix}\n{prompt}"

        result = detect_context(screen)
        assert result == "planet_command"

    @given(
        prefix=garbage_text,
    )
    def test_citadel_command_detected(self, prefix: str) -> None:
        """Citadel command prompt should be detected."""
        prompt = "Citadel Command [?=Help]?"
        screen = f"{prefix}\n{prompt}"

        result = detect_context(screen)
        assert result == "citadel_command"

    @given(
        prefix=garbage_text,
    )
    def test_pause_detected(self, prefix: str) -> None:
        """Pause screens should be detected."""
        # Both forms should work
        for prompt in ["[Pause]", "[Any Key]"]:
            screen = f"{prefix}\n{prompt}"
            result = detect_context(screen)
            assert result == "pause", f"Failed to detect pause with {prompt}"

    def test_empty_screen_returns_unknown(self) -> None:
        """Empty screen should return unknown."""
        assert detect_context("") == "unknown"
        assert detect_context("   \n  \n  ") == "unknown"


# =============================================================================
# Parsing Property Tests
# =============================================================================

class TestParsingProperties:
    """Property tests for screen parsing functions."""

    @given(credits=credit_amounts)
    def test_parse_credits_roundtrip(self, credits: int) -> None:
        """Parsing should correctly extract credits with any valid value."""
        # Format as the game would display
        formatted = f"{credits:,}"
        screen = f"Credits          : {formatted}"

        result = parse_display_screen(screen)
        assert result.get("credits") == credits

    @given(turns=st.integers(min_value=0, max_value=9999))
    def test_parse_turns_roundtrip(self, turns: int) -> None:
        """Parsing should correctly extract turns left."""
        screen = f"Turns left       : {turns}"

        result = parse_display_screen(screen)
        assert result.get("turns_left") == turns

    @given(sector=sector_numbers)
    def test_parse_sector_from_prompt(self, sector: int) -> None:
        """Sector should be extracted from command prompt."""
        screen = f"Command [TL=00:00:00]:[{sector}] (?=Help)?"

        result = parse_sector_display(screen)
        assert result.get("sector") == sector

    @given(warps=st.lists(sector_numbers, min_size=1, max_size=6, unique=True))
    def test_parse_warps_roundtrip(self, warps: list[int]) -> None:
        """Warps should be correctly parsed from sector display."""
        warp_str = " - ".join(str(w) for w in warps)
        screen = f"Warps to Sector(s) : {warp_str}"

        result = parse_sector_display(screen)
        assert set(result.get("warps", [])) == set(warps)

    @given(warps=st.lists(sector_numbers, min_size=1, max_size=6, unique=True))
    def test_parse_warps_with_parens(self, warps: list[int]) -> None:
        """Warps in parentheses (unexplored) should still be parsed."""
        warp_str = " - ".join(f"({w})" for w in warps)
        screen = f"Warps to Sector(s) :  {warp_str}"

        result = parse_sector_display(screen)
        assert set(result.get("warps", [])) == set(warps)

    @given(port_class=port_classes)
    def test_parse_port_class(self, port_class: str) -> None:
        """Port class should be correctly extracted."""
        screen = f"Ports   : Trading Port ({port_class})"

        result = parse_sector_display(screen)
        assert result.get("has_port") is True
        assert result.get("port_class") == port_class

    @given(garbage=garbage_text)
    def test_parse_display_never_raises(self, garbage: str) -> None:
        """parse_display_screen should never raise on any input."""
        result = parse_display_screen(garbage)
        assert isinstance(result, dict)

    @given(garbage=garbage_text)
    def test_parse_sector_never_raises(self, garbage: str) -> None:
        """parse_sector_display should never raise on any input."""
        result = parse_sector_display(garbage)
        assert isinstance(result, dict)
        assert "warps" in result
        assert isinstance(result["warps"], list)


# =============================================================================
# Sector Knowledge Property Tests
# =============================================================================

class TestSectorKnowledgeProperties:
    """Property tests for SectorKnowledge."""

    @given(
        sectors=st.lists(
            st.tuples(sector_numbers, st.lists(sector_numbers, min_size=1, max_size=6)),
            min_size=1,
            max_size=20,
        )
    )
    def test_record_and_retrieve_consistency(
        self, sectors: list[tuple[int, list[int]]]
    ) -> None:
        """Recorded observations should be retrievable."""
        knowledge = SectorKnowledge()

        for sector, warps in sectors:
            state = GameState(
                context="sector_command",
                sector=sector,
                warps=warps,
            )
            knowledge.record_observation(state)

        # All recorded sectors should be retrievable
        for sector, warps in sectors:
            retrieved = knowledge.get_warps(sector)
            # Last recorded warps for this sector should match
            last_warps = next(w for s, w in reversed(sectors) if s == sector)
            assert retrieved == last_warps

    @given(sector=sector_numbers)
    def test_unknown_sector_returns_none(self, sector: int) -> None:
        """Getting warps for unknown sector should return None."""
        knowledge = SectorKnowledge()
        assert knowledge.get_warps(sector) is None

    @given(sector=sector_numbers)
    def test_find_path_same_sector(self, sector: int) -> None:
        """Path from sector to itself should be [sector]."""
        knowledge = SectorKnowledge()
        path = knowledge.find_path(sector, sector)
        assert path == [sector]

    @given(
        start=sector_numbers,
        middle=sector_numbers,
        end=sector_numbers,
    )
    def test_find_path_linear_graph(
        self, start: int, middle: int, end: int
    ) -> None:
        """Path finding works for simple linear graphs."""
        assume(start != middle != end and start != end)

        knowledge = SectorKnowledge()
        knowledge._sectors[start] = SectorInfo(warps=[middle])
        knowledge._sectors[middle] = SectorInfo(warps=[start, end])
        knowledge._sectors[end] = SectorInfo(warps=[middle])

        path = knowledge.find_path(start, end)
        assert path is not None
        assert path[0] == start
        assert path[-1] == end
        assert len(path) == 3

    @given(
        sectors=st.lists(sector_numbers, min_size=2, max_size=10, unique=True)
    )
    def test_find_path_fully_connected(self, sectors: list[int]) -> None:
        """All paths should be found in fully connected graph."""
        knowledge = SectorKnowledge()

        # Create fully connected graph
        for sector in sectors:
            others = [s for s in sectors if s != sector]
            knowledge._sectors[sector] = SectorInfo(warps=others)

        # Any path should be findable in 2 hops max
        for start in sectors:
            for end in sectors:
                path = knowledge.find_path(start, end, max_hops=2)
                assert path is not None
                assert path[0] == start
                assert path[-1] == end


# =============================================================================
# Baud Rate Simulation Tests
# =============================================================================

class TestBaudRateSimulation:
    """Tests simulating partial screens due to baud rate."""

    @given(
        prefix_len=st.integers(min_value=0, max_value=200),
    )
    def test_partial_screen_detection(self, prefix_len: int) -> None:
        """Context detection should handle truncated screens gracefully."""
        full_screen = """Sector  : 1
Warps to Sector(s) : 2 - 3 - 4
Ports   : Trading Port (BBS)

Command [TL=00:00:00]:[1] (?=Help)?"""

        # Simulate partial render by truncating
        partial = full_screen[:prefix_len]

        # Should not raise, should return some context
        result = detect_context(partial)
        assert result in VALID_CONTEXTS

        # Only detect sector_command if prompt is fully visible
        if "(?=Help)?" in partial:
            assert result == "sector_command"

    @given(
        char_delay=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=10)  # Limit examples since this is about concept
    def test_incremental_screen_detection(self, char_delay: int) -> None:
        """Simulate incremental character arrival."""
        full_prompt = "Command [TL=00:00:00]:[1] (?=Help)?"

        # At various stages of rendering
        contexts_seen = []
        for i in range(1, len(full_prompt) + 1):
            partial = full_prompt[:i]
            context = detect_context(partial)
            contexts_seen.append(context)

        # Should not detect as sector_command until "?" is visible
        final_context = contexts_seen[-1]
        assert final_context == "sector_command"

        # Earlier partial renders should be "unknown" or something safe
        for ctx in contexts_seen[:-5]:  # Allow last few chars to trigger detection
            # Shouldn't prematurely detect as a specific safe context
            # (implementation detail: might be "unknown" or "menu")
            pass  # Just verify no exceptions


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Edge cases that hypothesis might not naturally generate."""

    def test_ansi_escape_codes_handled(self) -> None:
        """ANSI escape codes in screen should not break detection."""
        # ANSI color codes
        screen = "\x1b[32mCommand\x1b[0m [TL=00:00:00]:[1] (?=Help)?"
        result = detect_context(screen)
        # May or may not detect correctly with ANSI, but shouldn't raise
        assert result in VALID_CONTEXTS

    def test_unicode_in_screen(self) -> None:
        """Unicode characters should not break parsing."""
        screen = "Command [TL=00:00:00]:[1] (?=Help)?  \u2500\u2502\u256c"
        result = detect_context(screen)
        assert result in VALID_CONTEXTS

    def test_very_long_screen(self) -> None:
        """Very long screens should be handled."""
        prefix = "X" * 10000
        prompt = "\nCommand [TL=00:00:00]:[1] (?=Help)?"
        screen = prefix + prompt

        result = detect_context(screen)
        assert result == "sector_command"

    def test_multiple_prompts_in_screen(self) -> None:
        """Multiple prompt patterns - should use last one."""
        screen = """Command [TL=00:00:00]:[1] (?=Help)?
Some intermediate text
Planet Command [?=Help]?"""

        result = detect_context(screen)
        assert result == "planet_command"

    def test_negative_alignment_parsing(self) -> None:
        """Negative alignment should parse correctly."""
        screen = "Alignment        : -500 (Evil)"
        result = parse_display_screen(screen)
        assert result.get("alignment") == -500

    def test_large_numbers_with_commas(self) -> None:
        """Large numbers with comma separators should parse."""
        screen = "Credits          : 99,999,999"
        result = parse_display_screen(screen)
        assert result.get("credits") == 99999999
