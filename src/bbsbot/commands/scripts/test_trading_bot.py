#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for TW2002 Trading Bot."""

import pytest

from bbsbot.games.tw2002 import TradingBot


class TestTradingBot:
    """Test suite for TradingBot class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.bot = TradingBot()

    def test_parse_credits_basic(self):
        """Test credit parsing from screen."""
        screen = "Credits: 1,000,000\nOther text here"
        credits = self.bot._parse_credits_from_screen(screen)
        assert credits == 1_000_000

    def test_parse_credits_no_comma(self):
        """Test credit parsing without commas."""
        screen = "Credits: 5000\nOther text"
        credits = self.bot._parse_credits_from_screen(screen)
        assert credits == 5000

    def test_parse_credits_not_found(self):
        """Test credit parsing when credits not in screen."""
        screen = "Some other text\nNo credits here"
        # Should return current credits (0 by default)
        credits = self.bot._parse_credits_from_screen(screen)
        assert credits == 0

    def test_parse_sector_basic(self):
        """Test sector parsing from screen."""
        screen = "Sector 499\nCommand?"
        sector = self.bot._parse_sector_from_screen(screen)
        assert sector == 499

    def test_parse_sector_with_colon(self):
        """Test sector parsing with colon format."""
        screen = "Sector: 607\nOther text"
        sector = self.bot._parse_sector_from_screen(screen)
        assert sector == 607

    def test_parse_sector_not_found(self):
        """Test sector parsing when sector not in screen."""
        screen = "Some other text\nNo sector here"
        sector = self.bot._parse_sector_from_screen(screen)
        assert sector == 0

    def test_extract_game_options_basic(self):
        """Test game option extraction."""
        screen = """
Show Game Descriptions

<A> My Game
<B> Another Game

Select game (Q for none):
"""
        options = self.bot._extract_game_options(screen)
        assert len(options) == 2
        assert ("A", "My Game") in options
        assert ("B", "Another Game") in options

    def test_extract_game_options_bracket_format(self):
        """Test game option extraction with brackets."""
        screen = "[A] Trade Wars\n[B] Some Other Game"
        options = self.bot._extract_game_options(screen)
        assert len(options) == 2
        assert ("A", "Trade Wars") in options

    def test_extract_game_options_none_found(self):
        """Test when no game options found."""
        screen = "Some text without game options"
        options = self.bot._extract_game_options(screen)
        assert options == []

    def test_select_trade_wars_game_found(self):
        """Test selecting Trade Wars game."""
        screen = """
<A> Some Other Game
<B> Trade Wars 2002
<C> Yet Another Game
"""
        letter = self.bot._select_trade_wars_game(screen)
        assert letter == "B"

    def test_select_trade_wars_game_tw_abbrev(self):
        """Test selecting TW abbreviated game."""
        screen = "<A> TW2002\n<B> Other Game"
        letter = self.bot._select_trade_wars_game(screen)
        assert letter == "A"

    def test_select_trade_wars_game_first_fallback(self):
        """Test fallback to first game when Trade Wars not found."""
        screen = "<A> Some Game\n<B> Another Game"
        letter = self.bot._select_trade_wars_game(screen)
        assert letter == "A"  # Should default to first option

    def test_select_trade_wars_game_no_options(self):
        """Test when no games found."""
        screen = "No game options here"
        letter = self.bot._select_trade_wars_game(screen)
        assert letter == "A"  # Should default to "A"

    def test_clean_screen_for_display(self):
        """Test screen cleaning."""
        screen = """Line 1

Line 3

Line 5"""
        clean_lines = self.bot._clean_screen_for_display(screen, max_lines=10)
        # Should have removed the padding lines (80 spaces)
        assert len(clean_lines) == 3
        assert "Line 1" in clean_lines[0]
        assert "Line 3" in clean_lines[1]
        assert "Line 5" in clean_lines[2]

    def test_detect_error_invalid_password(self):
        """Test error detection for invalid password."""
        screen = "Invalid password! Try again."
        error = self.bot._detect_error_in_screen(screen)
        assert error == "invalid_password"

    def test_detect_error_insufficient_credits(self):
        """Test error detection for insufficient credits."""
        screen = "Not enough credits to complete this transaction."
        error = self.bot._detect_error_in_screen(screen)
        assert error == "insufficient_credits"

    def test_detect_error_hold_full(self):
        """Test error detection for hold full."""
        screen = "Your cargo hold is full!"
        error = self.bot._detect_error_in_screen(screen)
        assert error == "hold_full"

    def test_detect_error_ship_destroyed(self):
        """Test error detection for ship destroyed."""
        screen = "You are dead! Your ship was destroyed."
        error = self.bot._detect_error_in_screen(screen)
        assert error == "ship_destroyed"

    def test_detect_error_out_of_turns(self):
        """Test error detection for out of turns."""
        screen = "You have no turns remaining."
        error = self.bot._detect_error_in_screen(screen)
        assert error == "out_of_turns"

    def test_detect_error_none(self):
        """Test when no error in screen."""
        screen = "Normal game text here"
        error = self.bot._detect_error_in_screen(screen)
        assert error is None

    def test_check_for_loop_not_stuck(self):
        """Test loop detection when not stuck."""
        self.bot._check_for_loop("prompt.sector_command")
        self.bot._check_for_loop("prompt.port_menu")
        result = self.bot._check_for_loop("prompt.sector_command")
        assert result is False  # Different prompts, not stuck

    def test_check_for_loop_stuck(self):
        """Test loop detection when stuck."""
        # See same prompt 3 times
        self.bot._check_for_loop("prompt.twgs_select_game")
        self.bot._check_for_loop("prompt.twgs_select_game")
        result = self.bot._check_for_loop("prompt.twgs_select_game")
        assert result is True  # Stuck!

    def test_check_for_loop_reset(self):
        """Test loop detection resets with different prompts."""
        self.bot._check_for_loop("prompt.menu_a")
        self.bot._check_for_loop("prompt.menu_a")
        self.bot._check_for_loop("prompt.menu_b")  # Different prompt
        result = self.bot._check_for_loop("prompt.menu_a")
        assert result is False  # Counter reset


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
