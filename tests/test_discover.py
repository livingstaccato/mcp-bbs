# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for menu discovery."""

from __future__ import annotations

from bbsbot.learning.discovery import discover_menu


def test_discover_menu_with_brackets() -> None:
    """Test discovering menu with [X] style options."""
    screen = """
Main Menu

[A] Read messages
[B] Post message
[Q] Quit

Your choice:
    """
    result = discover_menu(screen)

    assert result["title"] == "Main Menu"
    assert result["prompt"] == "Your choice:"
    assert len(result["options"]) == 3
    assert result["options"][0]["key"] == "A"
    assert result["options"][0]["label"] == "Read messages"


def test_discover_menu_with_angle_brackets() -> None:
    """Test discovering menu with <X> style options."""
    screen = "<A> Option A\n<B> Option B"
    result = discover_menu(screen)

    assert len(result["options"]) == 2
    assert result["options"][0]["key"] == "A"


def test_discover_menu_with_parentheses() -> None:
    """Test discovering menu with X) style options."""
    screen = "1) First\n2) Second"
    result = discover_menu(screen)

    assert len(result["options"]) == 2
    assert result["options"][0]["key"] == "1"


def test_discover_menu_empty_screen() -> None:
    """Test discovering menu with empty screen."""
    result = discover_menu("")

    assert result["title"] == ""
    assert result["prompt"] == ""
    assert result["options"] == []
