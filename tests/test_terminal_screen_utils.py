# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from bbsbot.terminal.screen_utils import extract_action_tags, normalize_terminal_text


def test_normalize_terminal_text_strips_ansi_and_bare_sgr_fragments() -> None:
    raw = "41m\x1b[1;31mThere is no port in this sector!\x1b[0m\nCommand [TL=00:00:00]:[638] (?=Help)? :"
    cleaned = normalize_terminal_text(raw)
    assert "1;31m" not in cleaned
    assert "\x1b[" not in cleaned
    assert cleaned.startswith("There is no port in this sector!")


def test_extract_action_tags_from_screen() -> None:
    screen = """<Move>
Warps to Sector(s) :  148 - (386) - (608) - (633)
<Preparing ship to land on planet surface>
<Tow Control>
"""
    tags = extract_action_tags(screen)
    assert tags == ["Move", "Preparing ship to land on planet surface", "Tow Control"]
