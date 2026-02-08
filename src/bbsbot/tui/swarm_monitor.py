"""Live TUI dashboard for swarm monitoring.

Renders an htop-style terminal UI with real-time bot status
via WebSocket connection to the swarm manager.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import termios
import time
import tty

from bbsbot.defaults import MANAGER_URL

ANSI_RESET = "\x1b[0m"
ANSI_HIDE_CURSOR = "\x1b[?25l"
ANSI_SHOW_CURSOR = "\x1b[?25h"
ANSI_ALT_SCREEN = "\x1b[?1049h"
ANSI_EXIT_ALT = "\x1b[?1049l"
ANSI_BOLD = "\x1b[1m"
ANSI_DIM = "\x1b[2m"

# xterm-256color palette
FG_GREEN = "\x1b[38;5;82m"
FG_RED = "\x1b[38;5;196m"
FG_YELLOW = "\x1b[38;5;220m"
FG_CYAN = "\x1b[38;5;45m"
FG_BLUE = "\x1b[38;5;33m"
FG_WHITE = "\x1b[38;5;255m"
FG_GRAY = "\x1b[38;5;245m"
FG_ORANGE = "\x1b[38;5;208m"
BG_HEADER = "\x1b[48;5;236m"
BG_ROW_EVEN = "\x1b[48;5;234m"
BG_ROW_ODD = "\x1b[48;5;235m"
BG_SELECTED = "\x1b[48;5;238m"

STATE_COLORS = {
    "running": FG_GREEN,
    "paused": FG_YELLOW,
    "completed": FG_BLUE,
    "error": FG_RED,
    "stopped": FG_GRAY,
}

# Box drawing
BOX_H = "\u2500"
BOX_V = "\u2502"
BOX_TL = "\u250c"
BOX_TR = "\u2510"
BOX_BL = "\u2514"
BOX_BR = "\u2518"
BOX_T = "\u252c"
BOX_B = "\u2534"
BOX_L = "\u251c"
BOX_R = "\u2524"


def _move(row: int, col: int) -> str:
    return f"\x1b[{row};{col}H"


def _clear() -> str:
    return "\x1b[2J"


def _format_uptime(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m{s:02d}s"
    else:
        h, rem = divmod(int(seconds), 3600)
        m = rem // 60
        return f"{h}h{m:02d}m"


def _format_credits(credits: int) -> str:
    return f"{credits:,}"


def _bar(value: int, total: int, width: int) -> str:
    """Render a horizontal bar chart."""
    if total == 0:
        return " " * width
    filled = int((value / total) * width) if total else 0
    filled = min(filled, width)
    bar = "\u2588" * filled + "\u2591" * (width - filled)
    return bar


class SwarmMonitor:
    """Full-screen TUI dashboard for swarm monitoring."""

    def __init__(self, manager_url: str = MANAGER_URL) -> None:
        self.manager_url = manager_url
        self._dirty = True
        self._stop = False
        self._stdin_fd = sys.stdin.fileno()
        self._orig_term = termios.tcgetattr(self._stdin_fd)
        self._swarm_data: dict = {}
        self._selected_row = 0
        self._scroll_offset = 0
        self._sort_key = "bot_id"
        self._sort_reverse = False
        self._last_update = 0.0
        self._ws_connected = False
        self._error_msg = ""

    async def run(self) -> None:
        self._install_terminal()
        loop = asyncio.get_event_loop()
        try:
            loop.add_reader(self._stdin_fd, self._on_keypress)
            signal.signal(signal.SIGWINCH, lambda *_: self._mark_dirty())

            ws_task = asyncio.create_task(self._ws_loop())
            poll_task = asyncio.create_task(self._poll_loop())

            while not self._stop:
                if self._dirty:
                    self._render()
                    self._dirty = False
                await asyncio.sleep(0.05)

            ws_task.cancel()
            poll_task.cancel()
            with contextlib.suppress(Exception):
                await ws_task
            with contextlib.suppress(Exception):
                await poll_task
        finally:
            loop.remove_reader(self._stdin_fd)
            self._restore_terminal()

    def _install_terminal(self) -> None:
        tty.setcbreak(self._stdin_fd)
        sys.stdout.write(ANSI_ALT_SCREEN + ANSI_HIDE_CURSOR)
        sys.stdout.flush()

    def _restore_terminal(self) -> None:
        termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._orig_term)
        sys.stdout.write(ANSI_SHOW_CURSOR + ANSI_EXIT_ALT)
        sys.stdout.flush()

    def _mark_dirty(self) -> None:
        self._dirty = True

    async def _ws_loop(self) -> None:
        """Connect via WebSocket for real-time updates."""
        try:
            import websockets
        except ImportError:
            self._error_msg = "websockets not installed, using HTTP polling"
            self._dirty = True
            return

        ws_url = self.manager_url.replace("http", "ws") + "/ws/swarm"
        while not self._stop:
            try:
                async with websockets.connect(ws_url) as ws:
                    self._ws_connected = True
                    self._error_msg = ""
                    self._dirty = True
                    while not self._stop:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=5)
                            self._swarm_data = json.loads(msg)
                            self._last_update = time.time()
                            self._dirty = True
                        except TimeoutError:
                            # Send ping to keep alive
                            await ws.send("ping")
            except Exception:
                self._ws_connected = False
                self._dirty = True
                await asyncio.sleep(2)

    async def _poll_loop(self) -> None:
        """Fallback HTTP polling when WebSocket unavailable."""
        import httpx

        while not self._stop:
            if not self._ws_connected:
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{self.manager_url}/swarm/status",
                            timeout=5,
                        )
                        if resp.status_code == 200:
                            self._swarm_data = resp.json()
                            self._last_update = time.time()
                            self._dirty = True
                except Exception:
                    pass
            await asyncio.sleep(2)

    def _on_keypress(self) -> None:
        ch = os.read(self._stdin_fd, 3)
        if not ch:
            return
        key = ch.decode(errors="ignore")

        match key:
            case "q":
                self._stop = True
            case "j" | "\x1b[B":  # down
                self._selected_row += 1
            case "k" | "\x1b[A":  # up
                self._selected_row = max(0, self._selected_row - 1)
            case "s":
                self._cycle_sort()
            case "r":
                self._sort_reverse = not self._sort_reverse
            case _:
                pass
        self._dirty = True

    def _cycle_sort(self) -> None:
        keys = ["bot_id", "state", "sector", "credits", "turns_executed"]
        idx = keys.index(self._sort_key) if self._sort_key in keys else 0
        self._sort_key = keys[(idx + 1) % len(keys)]

    def _render(self) -> None:
        cols, rows = os.get_terminal_size()
        out: list[str] = []
        out.append(_clear())

        # ── Header ──
        out.append(_move(1, 1))
        out.append(BG_HEADER + ANSI_BOLD + FG_CYAN)
        title = " BBSBOT SWARM MONITOR "
        conn = f" {'WS' if self._ws_connected else 'HTTP'} "
        age = ""
        if self._last_update:
            age_s = time.time() - self._last_update
            age = f" {age_s:.0f}s ago "
        right = f"{conn}{age}"
        pad = cols - len(title) - len(right)
        out.append(title + " " * max(pad, 1) + FG_GRAY + right)
        out.append(ANSI_RESET)

        data = self._swarm_data
        if not data:
            out.append(_move(3, 2) + FG_YELLOW + "Waiting for data..." + ANSI_RESET)
            if self._error_msg:
                out.append(_move(4, 2) + FG_ORANGE + self._error_msg + ANSI_RESET)
            out.append(_move(rows, 1) + self._render_help_bar(cols))
            sys.stdout.write("".join(out))
            sys.stdout.flush()
            return

        row = 3
        row = self._render_summary(out, row, cols, data)
        row += 1
        row = self._render_bot_table(out, row, cols, rows, data)

        # Help bar at bottom
        out.append(_move(rows, 1) + self._render_help_bar(cols))

        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def _render_summary(
        self, out: list[str], row: int, cols: int, data: dict
    ) -> int:
        running = data.get("running", 0)
        total = data.get("total_bots", 0)
        completed = data.get("completed", 0)
        errors = data.get("errors", 0)
        credits = data.get("total_credits", 0)
        turns = data.get("total_turns", 0)
        uptime = data.get("uptime_seconds", 0)

        # Row 1: counts
        out.append(_move(row, 2))
        out.append(
            f"{FG_WHITE}Bots: {FG_GREEN}{running}{FG_WHITE}/{total}  "
            f"{FG_BLUE}Done: {completed}  "
            f"{FG_RED}Err: {errors}  "
            f"{FG_CYAN}Uptime: {_format_uptime(uptime)}"
            f"{ANSI_RESET}"
        )

        # Row 2: credits/turns + bar
        out.append(_move(row + 1, 2))
        bar_width = min(30, cols - 50)
        running_bar = _bar(running, max(total, 1), bar_width)
        out.append(
            f"{FG_WHITE}Credits: {FG_CYAN}{_format_credits(credits)}  "
            f"{FG_WHITE}Turns: {FG_CYAN}{turns:,}  "
            f"{FG_GREEN}{running_bar}"
            f"{ANSI_RESET}"
        )

        return row + 2

    def _render_bot_table(
        self, out: list[str], row: int, cols: int, total_rows: int, data: dict
    ) -> int:
        bots = data.get("bots", [])
        if not bots:
            out.append(_move(row, 2) + FG_GRAY + "No bots" + ANSI_RESET)
            return row + 1

        # Sort
        bots = sorted(
            bots,
            key=lambda b: b.get(self._sort_key, ""),
            reverse=self._sort_reverse,
        )

        # Column widths
        id_w = max(10, min(20, max(len(b.get("bot_id", "")) for b in bots) + 2))
        state_w = 12
        sector_w = 8
        credits_w = 14
        turns_w = 8
        config_w = max(0, cols - id_w - state_w - sector_w - credits_w - turns_w - 8)

        # Header
        out.append(_move(row, 1))
        out.append(BG_HEADER + ANSI_BOLD + FG_WHITE)
        hdr = (
            f" {'BOT ID':<{id_w}}"
            f"{'STATE':<{state_w}}"
            f"{'SECTOR':>{sector_w}}"
            f"{'CREDITS':>{credits_w}}"
            f"{'TURNS':>{turns_w}}"
        )
        if config_w > 5:
            hdr += f"  {'CONFIG':<{config_w}}"
        out.append(hdr.ljust(cols)[:cols])
        out.append(ANSI_RESET)
        row += 1

        # Separator
        out.append(_move(row, 1) + FG_GRAY + BOX_H * cols + ANSI_RESET)
        row += 1

        # Clamp selection
        max_display = total_rows - row - 2
        if max_display < 1:
            max_display = 1
        self._selected_row = max(0, min(self._selected_row, len(bots) - 1))

        # Scroll
        if self._selected_row >= self._scroll_offset + max_display:
            self._scroll_offset = self._selected_row - max_display + 1
        if self._selected_row < self._scroll_offset:
            self._scroll_offset = self._selected_row

        visible = bots[self._scroll_offset : self._scroll_offset + max_display]

        for i, bot in enumerate(visible):
            actual_idx = self._scroll_offset + i
            is_selected = actual_idx == self._selected_row
            bg = BG_SELECTED if is_selected else (BG_ROW_EVEN if i % 2 == 0 else BG_ROW_ODD)
            state = bot.get("state", "unknown")
            state_color = STATE_COLORS.get(state, FG_WHITE)

            bot_id = bot.get("bot_id", "?")
            sector = str(bot.get("sector", 0))
            credits = _format_credits(bot.get("credits", 0))
            turns = str(bot.get("turns_executed", 0))
            config = bot.get("config", "")

            line = (
                f" {bot_id:<{id_w}}"
                f"{state_color}{state:<{state_w}}{ANSI_RESET}{bg}"
                f"{sector:>{sector_w}}"
                f"{FG_CYAN}{credits:>{credits_w}}{ANSI_RESET}{bg}"
                f"{turns:>{turns_w}}"
            )
            if config_w > 5:
                config_short = config[-config_w:] if len(config) > config_w else config
                line += f"  {FG_GRAY}{config_short:<{config_w}}{ANSI_RESET}{bg}"

            out.append(_move(row, 1) + bg + line)
            padded_len = id_w + state_w + sector_w + credits_w + turns_w + 3
            if config_w > 5:
                padded_len += config_w + 2
            remaining = cols - padded_len
            if remaining > 0:
                out.append(" " * remaining)
            out.append(ANSI_RESET)
            row += 1

        return row

    def _render_help_bar(self, cols: int) -> str:
        keys = (
            f"{ANSI_BOLD}{FG_WHITE}q{ANSI_RESET}{FG_GRAY} quit  "
            f"{ANSI_BOLD}{FG_WHITE}j/k{ANSI_RESET}{FG_GRAY} nav  "
            f"{ANSI_BOLD}{FG_WHITE}s{ANSI_RESET}{FG_GRAY} sort:{self._sort_key}  "
            f"{ANSI_BOLD}{FG_WHITE}r{ANSI_RESET}{FG_GRAY} reverse"
            f"{ANSI_RESET}"
        )
        return BG_HEADER + keys + " " * max(cols - 60, 0) + ANSI_RESET
