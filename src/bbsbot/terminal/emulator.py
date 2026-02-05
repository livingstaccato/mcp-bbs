"""Terminal emulation using pyte."""

from __future__ import annotations

import hashlib
import time
from typing import Any

import pyte

from bbsbot.terminal.screen import parse_screen_text

# CP437 character encoding used by DOS/BBS systems
CP437 = "cp437"


class TerminalEmulator:
    """Terminal emulation using pyte."""

    def __init__(self, cols: int = 80, rows: int = 25, term: str = "ANSI") -> None:
        """Initialize terminal emulator.

        Args:
            cols: Terminal width in columns
            rows: Terminal height in rows
            term: Terminal type (e.g., "ANSI", "VT100")
        """
        self.cols = cols
        self.rows = rows
        self.term = term
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)

    def process(self, data: bytes) -> None:
        """Process raw bytes through terminal emulator.

        Args:
            data: Raw bytes to process (typically from transport)
        """
        # Decode from CP437 and feed to pyte
        text = data.decode(CP437, errors="replace")
        self._stream.feed(text)

    def _is_cursor_at_end(self) -> bool:
        """Check if cursor is at the end of visible content.

        Returns:
            True if cursor is at or near the end of the last line with content
        """
        cursor_x = self._screen.cursor.x
        cursor_y = self._screen.cursor.y

        # Find last line with content using display
        lines = self._screen.display
        for row_idx in range(len(lines) - 1, -1, -1):
            line = lines[row_idx].rstrip()
            if line:
                # Found last non-empty line
                if cursor_y == row_idx:
                    # Cursor is on last content line
                    # Check if at or near end (within 2 chars of line end)
                    return cursor_x >= len(line) - 2
                # Cursor is on a line below last content
                return cursor_y > row_idx

        # No content found, cursor is "at end"
        return True

    def get_snapshot(self) -> dict[str, Any]:
        """Get current screen state snapshot.

        Returns:
            Dictionary containing screen state:
                - screen: Screen text
                - screen_hash: SHA256 hash of screen text
                - cursor: Cursor position {x, y}
                - cols: Terminal columns
                - rows: Terminal rows
                - term: Terminal type
                - captured_at: Unix timestamp when snapshot was captured
                - cursor_at_end: True if cursor is at end of visible content
                - has_trailing_space: True if screen ends with space or colon
        """
        screen_text = parse_screen_text(self._screen)
        screen_hash = hashlib.sha256(screen_text.encode("utf-8")).hexdigest()

        return {
            "screen": screen_text,
            "screen_hash": screen_hash,
            "cursor": {"x": self._screen.cursor.x, "y": self._screen.cursor.y},
            "cols": self.cols,
            "rows": self.rows,
            "term": self.term,
            "captured_at": time.time(),
            "cursor_at_end": self._is_cursor_at_end(),
            "has_trailing_space": screen_text.rstrip() != screen_text.rstrip(" :"),
        }

    def reset(self) -> None:
        """Reset terminal to initial state."""
        self._screen.reset()

    def resize(self, cols: int, rows: int) -> None:
        """Resize terminal.

        Args:
            cols: New terminal width
            rows: New terminal height
        """
        self.cols = cols
        self.rows = rows
        self._screen.resize(cols, rows)
