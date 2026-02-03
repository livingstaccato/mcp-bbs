"""Terminal emulation using pyte."""

from __future__ import annotations

import hashlib

import pyte

from mcp_bbs.terminal.screen import parse_screen_text

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
        self._stream = pyte.ByteStream(self._screen)

    def process(self, data: bytes) -> None:
        """Process raw bytes through terminal emulator.

        Args:
            data: Raw bytes to process (typically from transport)
        """
        # Decode from CP437 and feed to pyte
        text = data.decode(CP437, errors="replace")
        self._stream.feed(text)

    def get_snapshot(self) -> dict:
        """Get current screen state snapshot.

        Returns:
            Dictionary containing screen state:
                - screen: Screen text
                - screen_hash: SHA256 hash of screen text
                - cursor: Cursor position {x, y}
                - cols: Terminal columns
                - rows: Terminal rows
                - term: Terminal type
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
