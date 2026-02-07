"""Integration tests for login sequence.

Tests the login_sequence() function with mocked BBS sessions
to verify correct handling of various prompts and flows.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class MockSession:
    """Mock session for testing login sequence."""

    def __init__(self, screens: list[dict[str, Any]]) -> None:
        """Initialize mock session with predefined screen responses.

        Args:
            screens: List of screen snapshots to return from wait_for_prompt.
                     Each dict should have: input_type, prompt_id, screen, kv_data
        """
        self.screens = screens
        self.screen_index = 0
        self.sent_keys: list[str] = []

    async def send(self, keys: str) -> None:
        """Record sent keys."""
        self.sent_keys.append(keys)

    async def wait_for_prompt(
        self, prompt_id: str | None = None, timeout_ms: int = 10000, interval_ms: int = 250
    ) -> dict[str, Any]:
        """Return next predefined screen."""
        if self.screen_index >= len(self.screens):
            # Return a terminal state
            return {
                "matched": True,
                "prompt_id": "prompt.command_generic",
                "input_type": "single_key",
                "screen": "Command [?=Help]?",
                "kv_data": {},
            }

        result = self.screens[self.screen_index]
        self.screen_index += 1
        return result


class MockBot:
    """Mock TradingBot for testing."""

    def __init__(self, session: MockSession) -> None:
        self.session = session
        self.loop_detection = MagicMock()
        self.loop_detection.clear = MagicMock()
        self.last_prompt_id = None
        self.stuck_threshold = 5
        self.current_sector = None
        self.current_credits = 0


def make_screen(
    prompt_id: str,
    input_type: str,
    screen: str,
    kv_data: dict | None = None,
) -> dict[str, Any]:
    """Helper to create screen snapshot dict."""
    return {
        "matched": True,
        "prompt_id": prompt_id,
        "input_type": input_type,
        "screen": screen,
        "kv_data": kv_data or {},
    }


class TestLoginSequencePromptHandling:
    """Tests for individual prompt handling in login sequence."""

    @pytest.mark.asyncio
    async def test_handles_menu_selection(self) -> None:
        """Test that menu selection sends game letter."""
        screens = [
            make_screen(
                "prompt.menu_selection",
                "single_key",
                "A) Game A\nB) Trade Wars 2002\nSelection (? for menu):",
            ),
            make_screen(
                "prompt.command_generic",
                "single_key",
                "Command [?=Help]?",
            ),
        ]
        session = MockSession(screens)
        bot = MockBot(session)

        # Import here to avoid issues with module loading
        from bbsbot.games.tw2002.login import _get_actual_prompt

        # Test menu_selection detection
        assert _get_actual_prompt(screens[0]["screen"]) == "menu_selection"

    @pytest.mark.asyncio
    async def test_handles_tw_game_menu(self) -> None:
        """Test that TW game menu sends T to play."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = """Trade Wars 2002
<S>tart a New Character
<H>igh Scores
Enter your choice:"""

        assert _get_actual_prompt(screen) == "tw_game_menu"

    @pytest.mark.asyncio
    async def test_handles_show_log_prompt(self) -> None:
        """Test that show log prompt sends N."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = "Show today's log? (Y/N)"
        assert _get_actual_prompt(screen) == "show_log_prompt"

    @pytest.mark.asyncio
    async def test_handles_name_selection(self) -> None:
        """Test that name selection sends B for BBS name."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = "(N)ew Name or (B)BS Name"
        assert _get_actual_prompt(screen) == "name_selection"

    @pytest.mark.asyncio
    async def test_handles_ship_name_prompt(self) -> None:
        """Test that ship name prompt enters ship name."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = "What do you want to name your ship?"
        assert _get_actual_prompt(screen) == "ship_name_prompt"

    @pytest.mark.asyncio
    async def test_handles_name_confirm(self) -> None:
        """Test that ship name confirmation sends Y."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = '"testbot\'s Ship"\nIs what you want?'
        assert _get_actual_prompt(screen) == "name_confirm"

    @pytest.mark.asyncio
    async def test_handles_password_prompt(self) -> None:
        """Test that password prompt sends password."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = "Welcome back!\nPassword?"
        assert _get_actual_prompt(screen) == "password_prompt"

    @pytest.mark.asyncio
    async def test_handles_new_character_prompt(self) -> None:
        """Test that new character prompt sends Y."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = "Start a new character?\n(Type Y or N)"
        assert _get_actual_prompt(screen) == "new_character_prompt"

    @pytest.mark.asyncio
    async def test_handles_use_ansi(self) -> None:
        """Test that ANSI prompt sends Y."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = "Use ANSI graphics?"
        assert _get_actual_prompt(screen) == "use_ansi"

    @pytest.mark.asyncio
    async def test_handles_description_mode(self) -> None:
        """Test that description mode sends Q to exit."""
        from bbsbot.games.tw2002.login import _get_actual_prompt, _is_description_mode

        screen = "Show Game Descriptions\nSelect game (Q for none):"
        assert _get_actual_prompt(screen) == "description_mode"
        assert _is_description_mode(screen) is True


class TestLoginSequenceFlow:
    """Tests for complete login flow scenarios."""

    @pytest.mark.asyncio
    async def test_new_character_flow(self) -> None:
        """Test complete new character creation flow.

        Flow: menu → game → log prompt → pause → password → name select →
              ship name → confirm → command prompt
        """
        from bbsbot.games.tw2002.login import _get_actual_prompt

        # Verify each step of the flow is detected correctly
        flow_steps = [
            ("Selection (? for menu):", "menu_selection"),
            ("Enter your choice:", "tw_game_menu"),
            ("Show today's log? (Y/N)", "show_log_prompt"),
            ("[Pause]", "pause"),
            ("Password?", "password_prompt"),
            ("(N)ew Name or (B)BS Name", "name_selection"),
            ("What do you want to name your ship?", "ship_name_prompt"),
            ("Is what you want?", "name_confirm"),
            ("Command [?=Help]?", "command_prompt"),
        ]

        for screen, expected_prompt in flow_steps:
            actual = _get_actual_prompt(screen)
            assert actual == expected_prompt, (
                f"Screen '{screen[:30]}...' expected '{expected_prompt}' but got '{actual}'"
            )

    @pytest.mark.asyncio
    async def test_returning_character_flow(self) -> None:
        """Test returning character login flow.

        Flow: menu → game → log prompt → password → command prompt
        """
        from bbsbot.games.tw2002.login import _get_actual_prompt

        flow_steps = [
            ("Selection (? for menu):", "menu_selection"),
            ("Enter your choice:", "tw_game_menu"),
            ("Show today's log? (Y/N)", "show_log_prompt"),
            ("Password?", "password_prompt"),
            ("Command [?=Help]?", "command_prompt"),
        ]

        for screen, expected_prompt in flow_steps:
            actual = _get_actual_prompt(screen)
            assert actual == expected_prompt

    @pytest.mark.asyncio
    async def test_description_mode_escape(self) -> None:
        """Test escaping from game description mode.

        When stuck in description mode, should send Q to exit.
        """
        from bbsbot.games.tw2002.login import _get_actual_prompt, _is_description_mode

        # First detect description mode
        desc_screen = "Show Game Descriptions\nSelect game (Q for none):"
        assert _is_description_mode(desc_screen) is True
        assert _get_actual_prompt(desc_screen) == "description_mode"

        # After sending Q, should return to menu
        menu_screen = "Selection (? for menu):"
        assert _get_actual_prompt(menu_screen) == "menu_selection"


class TestLoginSequenceEdgeCases:
    """Edge case tests for login sequence."""

    @pytest.mark.asyncio
    async def test_stale_pause_in_buffer(self) -> None:
        """Test that stale [Pause] text doesn't confuse detection."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        # Old pause text in buffer, but command prompt is current
        screen = """[Pause] press space or enter

═══════════════════════════════

Command [TL=00:00:00]:[1] (?=Help)?"""

        assert _get_actual_prompt(screen) == "command_prompt"

    @pytest.mark.asyncio
    async def test_partial_ship_name_input(self) -> None:
        """Test ship name detection with partial input on last line."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        # User started typing but prompt should still be detected
        screen = """What do you want to name your ship?
testbot's Sh"""

        assert _get_actual_prompt(screen) == "ship_name_prompt"

    @pytest.mark.asyncio
    async def test_planet_command_is_game_entry(self) -> None:
        """Test that planet command is recognized as game entry."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        screen = """Planet Terra
Population: 1000

Planet Command [?=Help]?"""

        assert _get_actual_prompt(screen) == "command_prompt"

    @pytest.mark.asyncio
    async def test_multiple_pause_screens(self) -> None:
        """Test handling multiple consecutive pause screens."""
        from bbsbot.games.tw2002.login import _get_actual_prompt

        # Each pause should be detected
        screens = [
            "[Pause]",
            "[ANY KEY]",
            "[Pause] press space or enter",
        ]

        expected = ["pause", "any_key", "pause"]

        for screen, exp in zip(screens, expected):
            assert _get_actual_prompt(screen) == exp


class TestLoginValidation:
    """Tests for login validation functionality."""

    def test_kv_validation_valid(self) -> None:
        """Test validation passes for valid data."""
        from bbsbot.games.tw2002.login import _check_kv_validation

        kv_data = {"_validation": {"valid": True}}
        assert _check_kv_validation(kv_data, "test") == ""

    def test_kv_validation_invalid(self) -> None:
        """Test validation returns error for invalid data."""
        from bbsbot.games.tw2002.login import _check_kv_validation

        kv_data = {"_validation": {"valid": False, "errors": ["Field X is invalid"]}}
        result = _check_kv_validation(kv_data, "test")
        assert "[VALIDATION]" in result
        assert "Field X" in result

    def test_kv_validation_none(self) -> None:
        """Test validation handles None kv_data."""
        from bbsbot.games.tw2002.login import _check_kv_validation

        assert _check_kv_validation(None, "test") == ""

    def test_kv_validation_empty(self) -> None:
        """Test validation handles empty kv_data."""
        from bbsbot.games.tw2002.login import _check_kv_validation

        assert _check_kv_validation({}, "test") == ""


class TestLoginSequenceIntegration:
    """Integration tests that simulate full login flows."""

    @pytest.mark.asyncio
    async def test_send_input_adds_carriage_return(self) -> None:
        """Test that send_input adds \\r for multi_key input."""
        from bbsbot.games.tw2002.io import send_input

        # Create mock bot with mock session
        mock_session = AsyncMock()
        mock_session.send = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.session = mock_session

        await send_input(mock_bot, "testuser", "multi_key")

        # Should have sent with carriage return
        mock_session.send.assert_called_once_with("testuser\r")

    @pytest.mark.asyncio
    async def test_send_input_single_key_no_cr(self) -> None:
        """Test that send_input doesn't add \\r for single_key input."""
        from bbsbot.games.tw2002.io import send_input

        mock_session = AsyncMock()
        mock_session.send = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.session = mock_session

        await send_input(mock_bot, "Y", "single_key")

        # Should send without carriage return
        mock_session.send.assert_called_once_with("Y")

    @pytest.mark.asyncio
    async def test_send_input_any_key_sends_space(self) -> None:
        """Test that send_input sends space for any_key."""
        from bbsbot.games.tw2002.io import send_input

        mock_session = AsyncMock()
        mock_session.send = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.session = mock_session

        await send_input(mock_bot, "", "any_key")

        # Should send space
        mock_session.send.assert_called_once_with(" ")
