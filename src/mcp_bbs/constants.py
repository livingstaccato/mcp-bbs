"""Shared constants for mcp-bbs."""

from __future__ import annotations

# Character encoding used by DOS/BBS systems
CP437 = "cp437"

# Default terminal settings
DEFAULT_COLS = 80
DEFAULT_ROWS = 25
DEFAULT_TERM = "ANSI"

# Default timeouts
DEFAULT_READ_TIMEOUT_MS = 250
DEFAULT_MAX_BYTES = 8192
DEFAULT_CONNECT_TIMEOUT_S = 30.0

# Session limits
DEFAULT_MAX_SESSIONS = 10
