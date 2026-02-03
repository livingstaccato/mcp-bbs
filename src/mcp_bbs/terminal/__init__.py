"""Terminal emulation layer."""

from __future__ import annotations

from mcp_bbs.terminal.emulator import TerminalEmulator
from mcp_bbs.terminal.screen import parse_screen_text

__all__ = ["TerminalEmulator", "parse_screen_text"]
