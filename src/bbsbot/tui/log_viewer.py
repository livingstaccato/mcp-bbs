"""TUI log viewer overlay for the swarm monitor.

Renders a scrollable log view in the bottom portion of the terminal,
streaming logs via HTTP polling from the manager API.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque

from bbsbot.defaults import MANAGER_URL
from bbsbot.logging import get_logger

logger = get_logger(__name__)

ANSI_RESET = "\x1b[0m"
ANSI_BOLD = "\x1b[1m"
FG_CYAN = "\x1b[38;5;45m"
FG_WHITE = "\x1b[38;5;255m"
FG_GRAY = "\x1b[38;5;245m"
FG_GREEN = "\x1b[38;5;82m"
FG_RED = "\x1b[38;5;196m"
BG_OVERLAY = "\x1b[48;5;233m"
BG_HEADER = "\x1b[48;5;236m"

MAX_LINES = 2000


def _move(row: int, col: int) -> str:
    return f"\x1b[{row};{col}H"


class LogViewerOverlay:
    """Overlay that shows streaming logs for a selected bot."""

    def __init__(self, manager_url: str = MANAGER_URL) -> None:
        self.manager_url = manager_url
        self.bot_id: str = ""
        self.lines: deque[str] = deque(maxlen=MAX_LINES)
        self.scroll_offset: int = 0
        self.active: bool = False
        self._stream_task: asyncio.Task | None = None
        self._connected: bool = False

    def open(self, bot_id: str) -> None:
        """Open the log viewer for a bot."""
        self.bot_id = bot_id
        self.lines.clear()
        self.scroll_offset = 0
        self.active = True
        self._connected = False
        self._start_stream()

    def close(self) -> None:
        """Close the log viewer."""
        self.active = False
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = None

    def scroll_up(self, amount: int = 3) -> None:
        self.scroll_offset = min(
            self.scroll_offset + amount,
            max(0, len(self.lines) - 1),
        )

    def scroll_down(self, amount: int = 3) -> None:
        self.scroll_offset = max(0, self.scroll_offset - amount)

    def scroll_to_bottom(self) -> None:
        self.scroll_offset = 0

    def _start_stream(self) -> None:
        """Start the WebSocket log stream."""
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = asyncio.create_task(self._ws_stream())

    async def _ws_stream(self) -> None:
        """Stream logs via WebSocket."""
        try:
            import websockets
        except ImportError:
            self.lines.append("[websockets not installed - falling back to HTTP]")
            await self._http_poll()
            return

        ws_url = self.manager_url.replace("http", "ws") + f"/ws/bot/{self.bot_id}/logs"
        try:
            async with websockets.connect(ws_url) as ws:
                self._connected = True
                while self.active:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        data = json.loads(msg)
                        if data.get("lines"):
                            if data.get("type") == "truncated":
                                self.lines.clear()
                            for line in data["lines"]:
                                self.lines.append(line)
                            # Auto-scroll to bottom on new data if already at bottom
                            if self.scroll_offset == 0:
                                pass  # Already at bottom
                    except TimeoutError:
                        pass
        except asyncio.CancelledError:
            return
        except Exception:
            self._connected = False
            if self.active:
                self.lines.append("[WebSocket disconnected - retrying...]")
                await asyncio.sleep(2)
                if self.active:
                    self._start_stream()

    async def _http_poll(self) -> None:
        """Fallback: poll logs via HTTP."""
        import httpx

        last_total = 0
        while self.active:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{self.manager_url}/bot/{self.bot_id}/logs/tail",
                        params={"lines": 100},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        new_total = data.get("total_lines", 0)
                        if new_total != last_total:
                            self.lines.clear()
                            for line in data.get("lines", []):
                                self.lines.append(line)
                            last_total = new_total
                            self._connected = True
            except Exception:
                self._connected = False
            await asyncio.sleep(1)

    def render(self, start_row: int, end_row: int, cols: int) -> str:
        """Render the overlay into the given terminal region.

        Args:
            start_row: First row (1-indexed)
            end_row: Last row (1-indexed)
            cols: Terminal width

        Returns:
            ANSI string to write
        """
        if not self.active:
            return ""

        out: list[str] = []
        height = end_row - start_row

        # Header bar
        out.append(_move(start_row, 1))
        status = f"{FG_GREEN}LIVE" if self._connected else f"{FG_RED}..."
        title = f" LOGS: {self.bot_id} "
        hint = " ESC close  j/k scroll  G bottom "
        pad = cols - len(title) - len(hint) - 8
        out.append(
            BG_HEADER
            + ANSI_BOLD
            + FG_CYAN
            + title
            + FG_GRAY
            + " " * max(pad, 1)
            + status
            + ANSI_RESET
            + BG_HEADER
            + FG_GRAY
            + hint
            + " " * max(cols - len(title) - len(hint) - max(pad, 1) - 8, 0)
            + ANSI_RESET
        )

        # Separator
        out.append(_move(start_row + 1, 1))
        out.append(FG_GRAY + "\u2500" * cols + ANSI_RESET)

        # Log lines (bottom-up, scroll_offset=0 means latest at bottom)
        visible_height = height - 2  # subtract header + separator
        all_lines = list(self.lines)
        total = len(all_lines)

        if total == 0:
            out.append(_move(start_row + 2, 2))
            out.append(BG_OVERLAY + FG_GRAY + "Waiting for logs..." + ANSI_RESET)
            # Fill remaining rows
            for r in range(start_row + 3, end_row + 1):
                out.append(_move(r, 1) + BG_OVERLAY + " " * cols + ANSI_RESET)
            return "".join(out)

        # Calculate visible window
        end_idx = total - self.scroll_offset
        start_idx = max(0, end_idx - visible_height)
        visible = all_lines[start_idx:end_idx]

        for i, line in enumerate(visible):
            row = start_row + 2 + i
            if row > end_row:
                break
            # Truncate line to terminal width
            display = line[: cols - 2] if len(line) > cols - 2 else line
            pad_len = cols - len(display) - 1
            out.append(_move(row, 1) + BG_OVERLAY + FG_WHITE + " " + display + " " * max(pad_len, 0) + ANSI_RESET)

        # Fill any remaining rows
        filled = len(visible)
        for i in range(filled, visible_height):
            row = start_row + 2 + i
            if row > end_row:
                break
            out.append(_move(row, 1) + BG_OVERLAY + " " * cols + ANSI_RESET)

        return "".join(out)
