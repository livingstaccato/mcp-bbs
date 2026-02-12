# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Terminal emulation layer."""

from __future__ import annotations

from bbsbot.terminal.emulator import TerminalEmulator
from bbsbot.terminal.screen import parse_screen_text
from bbsbot.terminal.screen_utils import (
    clean_screen_for_display,
    extract_key_value_pairs,
    extract_menu_options,
    extract_numbered_list,
    strip_ansi_codes,
)

__all__ = [
    "TerminalEmulator",
    "parse_screen_text",
    "clean_screen_for_display",
    "extract_key_value_pairs",
    "extract_menu_options",
    "extract_numbered_list",
    "strip_ansi_codes",
]
