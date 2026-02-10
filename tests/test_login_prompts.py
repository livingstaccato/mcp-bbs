"""Unit tests for login prompt detection.

Tests the _get_actual_prompt() function which analyzes screen content
to determine the actual prompt type based on last-line analysis.
"""

from __future__ import annotations

from bbsbot.games.tw2002.login import _get_actual_prompt, _is_description_mode


class TestGetActualPrompt:
    """Tests for _get_actual_prompt() function."""

    def test_command_prompt_with_question_mark(self) -> None:
        """Test detection of command prompt with ?."""
        screen = """
Sector  : 1
Warps   : 2, 3, 5
Ports   : None

Command [TL=00:00:00]:[1] (?=Help)?"""
        assert _get_actual_prompt(screen) == "command_prompt"

    def test_command_prompt_sector_command(self) -> None:
        """Test detection of sector command prompt."""
        screen = """
Sector  : 42
Fighters: 0

Sector Command [?=Help]?"""
        assert _get_actual_prompt(screen) == "command_prompt"

    def test_planet_command_prompt(self) -> None:
        """Test detection of planet command prompt."""
        screen = """
Planet Terra
Population: 1000
Ore: 500

Planet Command [?=Help]?"""
        assert _get_actual_prompt(screen) == "command_prompt"

    def test_tw_game_menu(self) -> None:
        """Test detection of TW2002 pre-game menu."""
        screen = """
Trade Wars 2002
═══════════════
<S>tart a New Character
<H>igh Scores
<M>essage Board
<X>it Game

Enter your choice:"""
        assert _get_actual_prompt(screen) == "tw_game_menu"

    def test_name_selection_prompt(self) -> None:
        """Test detection of name selection (N)ew or (B)BS."""
        screen = """
Welcome to Trade Wars 2002!

You are creating a new character.

(N)ew Name or (B)BS Name"""
        assert _get_actual_prompt(screen) == "name_selection"

    def test_password_prompt(self) -> None:
        """Test detection of password prompt."""
        screen = """
Welcome back, testbot!

Password?"""
        assert _get_actual_prompt(screen) == "password_prompt"

    def test_password_prompt_not_partial(self) -> None:
        """Test that password prompt is only detected on last line."""
        # This should NOT match - password text is not on last line
        screen = """
Password? test
Welcome to the game!

Command [?=Help]?"""
        assert _get_actual_prompt(screen) == "command_prompt"

    def test_new_character_prompt(self) -> None:
        """Test detection of new character creation prompt."""
        screen = """
testbot is not in the game.

Do you want to start a new character?
(Type Y or N)"""
        assert _get_actual_prompt(screen) == "new_character_prompt"

    def test_new_character_prompt_already_answered(self) -> None:
        """Test that answered new character prompt is not detected."""
        # When "Yes" appears on the same line, it's already answered
        screen = """
Do you want to start a new character?
(Type Y or N) Yes

Creating character..."""
        # Should not return new_character_prompt since it's answered
        assert _get_actual_prompt(screen) != "new_character_prompt"

    def test_game_full_prompt(self) -> None:
        """Test detection of game-full rejection during new-character flow."""
        screen = """
Do you want to start a new character?
(Type Y or N) Yes
Yes I'm sorry but the game is full."""
        assert _get_actual_prompt(screen) == "game_full"

    def test_show_log_prompt(self) -> None:
        """Test detection of show today's log prompt."""
        screen = """
═══════════════════════════════
Trade Wars 2002
═══════════════════════════════

Show today's log? (Y/N)"""
        assert _get_actual_prompt(screen) == "show_log_prompt"

    def test_generic_yes_no_prompt(self) -> None:
        """Test detection of generic Y/N prompt."""
        screen = """
Are you sure you want to quit?

(Y/N)"""
        assert _get_actual_prompt(screen) == "yes_no_prompt"

    def test_what_is_your_name(self) -> None:
        """Test detection of name prompt."""
        screen = """
Trade Wars 2002 Character Creation

What is your name?"""
        assert _get_actual_prompt(screen) == "what_is_your_name"

    def test_use_ansi_graphics(self) -> None:
        """Test detection of ANSI graphics prompt."""
        screen = """
Welcome to Trade Wars 2002!

Use ANSI graphics?"""
        assert _get_actual_prompt(screen) == "use_ansi"

    def test_name_confirm(self) -> None:
        """Test detection of ship name confirmation."""
        screen = """
You have chosen to name your ship:
  "testbot's Ship"

Is what you want?"""
        assert _get_actual_prompt(screen) == "name_confirm"

    def test_ship_name_prompt(self) -> None:
        """Test detection of ship naming prompt."""
        screen = """
Congratulations! You are now a trader.

What do you want to name your ship?"""
        assert _get_actual_prompt(screen) == "ship_name_prompt"

    def test_ship_name_prompt_with_partial_input(self) -> None:
        """Test ship name prompt detection when partial input is on last line."""
        # When user has started typing, the prompt text is above the last line
        screen = """
Congratulations! You are now a trader.

What do you want to name your ship?
testbot's S"""
        # Should still detect ship_name_prompt by checking last_lines
        assert _get_actual_prompt(screen) == "ship_name_prompt"

    def test_any_key_prompt(self) -> None:
        """Test detection of [ANY KEY] prompt."""
        screen = """
═══════════════════════════════
      TRADE WARS 2002
═══════════════════════════════

[ANY KEY]"""
        assert _get_actual_prompt(screen) == "any_key"

    def test_pause_prompt(self) -> None:
        """Test detection of [Pause] prompt on last line."""
        screen = """
Welcome message content...
More content...

[Pause]"""
        assert _get_actual_prompt(screen) == "pause"

    def test_pause_not_stale_buffer(self) -> None:
        """Test that stale [Pause] in buffer is not detected."""
        # [Pause] is NOT on the last line - this is stale buffer content
        screen = """
[Pause] press space or enter

This is newer content

Command [?=Help]?"""
        # Should detect command_prompt, not pause
        assert _get_actual_prompt(screen) == "command_prompt"

    def test_menu_selection(self) -> None:
        """Test detection of menu selection prompt."""
        screen = """
TWGS Game Selection
═══════════════════
A) Trade Wars Game A
B) AI Apocalypse

Selection (? for menu):"""
        assert _get_actual_prompt(screen) == "menu_selection"

    def test_description_mode(self) -> None:
        """Test detection of game description mode."""
        screen = """
Show Game Descriptions
A) Trade Wars
B) AI Apocalypse

Select game (Q for none):"""
        assert _get_actual_prompt(screen) == "description_mode"

    def test_empty_screen(self) -> None:
        """Test handling of empty screen."""
        assert _get_actual_prompt("") == ""
        assert _get_actual_prompt("   \n   \n   ") == ""

    def test_alias_prompt(self) -> None:
        """Test detection of alias prompt when name is taken."""
        screen = """
Sorry, you cannot use the name claude, its already in use.
You must use an Alias.
What Alias do you want to use?"""
        assert _get_actual_prompt(screen) == "alias_prompt"

    def test_alias_prompt_with_partial_input(self) -> None:
        """Test alias prompt detection with partial input."""
        screen = """
Sorry, you cannot use the name claude, its already in use.
You must use an Alias.
What Alias do you want to use? clau"""
        assert _get_actual_prompt(screen) == "alias_prompt"

    def test_alias_prompt_priority_over_name_selection(self) -> None:
        """Test that alias prompt takes priority over stale name_selection."""
        screen = """
Use (N)ew Name or (B)BS Name [B] ? B
Sorry, you cannot use the name claude, its already in use.
You must use an Alias.
What Alias do you want to use?"""
        # Should detect alias_prompt, not name_selection
        assert _get_actual_prompt(screen) == "alias_prompt"

    def test_unknown_prompt(self) -> None:
        """Test that unknown content returns empty string."""
        screen = """
Some random content
That doesn't match any prompts
Just regular text here"""
        assert _get_actual_prompt(screen) == ""


class TestIsDescriptionMode:
    """Tests for _is_description_mode() function."""

    def test_show_game_descriptions(self) -> None:
        """Test detection of 'Show Game Descriptions' text."""
        screen = "Show Game Descriptions\nSelect game (Q for none):"
        assert _is_description_mode(screen) is True

    def test_select_game_q_for_none(self) -> None:
        """Test detection of 'Select game (Q for none)' text."""
        screen = "Some content\nSelect game (Q for none):"
        assert _is_description_mode(screen) is True

    def test_normal_game_selection(self) -> None:
        """Test that normal game selection is not description mode."""
        screen = "Selection (? for menu):\nA) Game A\nB) Game B"
        assert _is_description_mode(screen) is False

    def test_in_game_screen(self) -> None:
        """Test that in-game screen is not description mode."""
        screen = "Sector 1\nCommand [?=Help]?"
        assert _is_description_mode(screen) is False


class TestPromptPriority:
    """Tests for prompt detection priority.

    When multiple patterns could match, ensure the correct one is detected.
    """

    def test_show_log_over_generic_yes_no(self) -> None:
        """Test that show_log_prompt takes priority over yes_no_prompt."""
        screen = "Show today's log? (Y/N)"
        assert _get_actual_prompt(screen) == "show_log_prompt"

    def test_new_character_over_generic_yes_no(self) -> None:
        """Test new_character_prompt detection with (Type Y or N)."""
        screen = """
Do you want to start a new character?
(Type Y or N)"""
        assert _get_actual_prompt(screen) == "new_character_prompt"

    def test_command_prompt_priority(self) -> None:
        """Test command prompt detected even with other content above."""
        screen = """
[Pause] - old buffer content
Show today's log? - old prompt
═══════════════════════════════

Command [TL=00:00:00]:[1] (?=Help)?"""
        # Last line is command prompt, should take priority
        assert _get_actual_prompt(screen) == "command_prompt"


class TestEdgeCases:
    """Edge case tests for prompt detection."""

    def test_case_insensitivity(self) -> None:
        """Test that detection is case-insensitive."""
        assert _get_actual_prompt("COMMAND [?=HELP]?") == "command_prompt"
        assert _get_actual_prompt("command [?=help]?") == "command_prompt"
        assert _get_actual_prompt("Planet Command [?=Help]?") == "command_prompt"

    def test_whitespace_handling(self) -> None:
        """Test that whitespace is handled correctly."""
        screen = """


Command [?=Help]?

"""
        assert _get_actual_prompt(screen) == "command_prompt"

    def test_long_screen_content(self) -> None:
        """Test with many lines of content."""
        lines = ["Line " + str(i) for i in range(100)]
        lines.append("Command [?=Help]?")
        screen = "\n".join(lines)
        assert _get_actual_prompt(screen) == "command_prompt"

    def test_ansi_escape_codes_stripped(self) -> None:
        """Test that ANSI codes in content don't break detection.

        Note: The screen content passed to _get_actual_prompt should already
        have ANSI codes processed by pyte, but we test robustness.
        """
        # Simple case without actual ANSI codes (pyte strips them)
        screen = "Command [?=Help]?"
        assert _get_actual_prompt(screen) == "command_prompt"
