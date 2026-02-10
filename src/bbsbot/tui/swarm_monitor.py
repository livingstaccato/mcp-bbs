"""Live TUI dashboard for swarm monitoring."""

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
from bbsbot.tui.log_viewer import LogViewerOverlay

ANSI_RESET = "\x1b[0m"
ANSI_HIDE_CURSOR = "\x1b[?25l"
ANSI_SHOW_CURSOR = "\x1b[?25h"
ANSI_ALT_SCREEN = "\x1b[?1049h"
ANSI_EXIT_ALT = "\x1b[?1049l"
ANSI_BOLD = "\x1b[1m"

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
    "completed": FG_BLUE,
    "error": FG_RED,
    "stopped": FG_GRAY,
}

BOX_H = "\u2500"


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
    if total == 0:
        return " " * width
    filled = int((value / total) * width) if total else 0
    filled = min(filled, width)
    return "\u2588" * filled + "\u2591" * (width - filled)


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
        self._log_viewer = LogViewerOverlay(manager_url)
        self._confirm_action: str | None = None  # "kill" or "restart"
        self._confirm_bot_id: str | None = None

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
            self._log_viewer.close()
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

    def _get_selected_bot_id(self) -> str | None:
        """Get the bot_id of the currently selected row."""
        bots = self._get_sorted_bots()
        if 0 <= self._selected_row < len(bots):
            return bots[self._selected_row].get("bot_id")
        return None

    def _get_sorted_bots(self) -> list[dict]:
        bots = self._swarm_data.get("bots", [])
        return sorted(
            bots,
            key=lambda b: b.get(self._sort_key, ""),
            reverse=self._sort_reverse,
        )

    async def _ws_loop(self) -> None:
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
                            await ws.send("ping")
            except Exception:
                self._ws_connected = False
                self._dirty = True
                await asyncio.sleep(2)

    async def _poll_loop(self) -> None:
        import httpx

        while not self._stop:
            if not self._ws_connected:
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{self.manager_url}/swarm/status", timeout=5,
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

        # Handle confirmation dialog
        if self._confirm_action:
            match key:
                case "y" | "Y":
                    bot_id = self._confirm_bot_id
                    action = self._confirm_action
                    self._confirm_action = None
                    self._confirm_bot_id = None
                    if bot_id:
                        asyncio.create_task(self._execute_action(action, bot_id))
                case _:
                    self._confirm_action = None
                    self._confirm_bot_id = None
            self._dirty = True
            return

        # Handle log viewer keys
        if self._log_viewer.active:
            match key:
                case "\x1b" | "\x1b\x1b":  # ESC
                    self._log_viewer.close()
                case "k" | "\x1b[A":  # up
                    self._log_viewer.scroll_up()
                case "j" | "\x1b[B":  # down
                    self._log_viewer.scroll_down()
                case "G":
                    self._log_viewer.scroll_to_bottom()
                case "q":
                    self._log_viewer.close()
            self._dirty = True
            return

        # Main view keys
        match key:
            case "q":
                self._stop = True
            case "j" | "\x1b[B":
                self._selected_row += 1
            case "k" | "\x1b[A":
                self._selected_row = max(0, self._selected_row - 1)
            case "s":
                self._cycle_sort()
            case "r":
                self._sort_reverse = not self._sort_reverse
            case "l" | "\r":  # l or Enter - open logs
                bot_id = self._get_selected_bot_id()
                if bot_id:
                    self._log_viewer.open(bot_id)
            case "K":  # Kill (capital K)
                bot_id = self._get_selected_bot_id()
                if bot_id:
                    self._confirm_action = "kill"
                    self._confirm_bot_id = bot_id
            case "R":  # Restart (capital R)
                bot_id = self._get_selected_bot_id()
                if bot_id:
                    self._confirm_action = "restart"
                    self._confirm_bot_id = bot_id
            case _:
                pass
        self._dirty = True

    async def _execute_action(self, action: str, bot_id: str) -> None:
        """Execute a kill or restart action via HTTP."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                match action:
                    case "kill":
                        await client.delete(
                            f"{self.manager_url}/bot/{bot_id}", timeout=10,
                        )
                    case "restart":
                        await client.post(
                            f"{self.manager_url}/bot/{bot_id}/restart", timeout=10,
                        )
        except Exception:
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

        # Header
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

        # Calculate split: if log viewer is active, table gets top 30%
        if self._log_viewer.active:
            table_end_row = max(8, rows * 30 // 100)
            log_start_row = table_end_row + 1
        else:
            table_end_row = rows - 1  # leave room for help bar
            log_start_row = rows

        row = 3
        row = self._render_summary(out, row, cols, data)
        row += 1
        row = self._render_bot_table(out, row, cols, table_end_row, data)

        # Log viewer overlay
        if self._log_viewer.active:
            out.append(self._log_viewer.render(log_start_row, rows - 1, cols))

        # Confirm dialog
        if self._confirm_action and self._confirm_bot_id:
            out.append(self._render_confirm(rows, cols))

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

        out.append(_move(row, 2))
        out.append(
            f"{FG_WHITE}Bots: {FG_GREEN}{running}{FG_WHITE}/{total}  "
            f"{FG_BLUE}Done: {completed}  "
            f"{FG_RED}Err: {errors}  "
            f"{FG_CYAN}Uptime: {_format_uptime(uptime)}"
            f"{ANSI_RESET}"
        )

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
        bots = self._get_sorted_bots()
        if not bots:
            out.append(_move(row, 2) + FG_GRAY + "No bots" + ANSI_RESET)
            return row + 1

        def _shorten(s: str, w: int) -> str:
            s = str(s or "")
            if w <= 0:
                return ""
            if len(s) <= w:
                return s.ljust(w)
            if w <= 3:
                return s[:w]
            # Keep head/tail to preserve identity across updates.
            head = max(1, (w - 1) // 2)
            tail = max(1, w - head - 1)
            return (s[:head] + "…" + s[-tail:])[:w]

        # Fixed widths to avoid jitter as values change.
        id_w = 14
        state_w = 10
        status_w = 18
        strat_w = 18
        sector_w = 6
        credits_w = 10
        fuel_w = 5
        org_w = 5
        equip_w = 5
        turns_w = 7
        act_w = 12

        want_status = cols >= (id_w + state_w + status_w + sector_w + credits_w + turns_w + act_w + 10)
        want_strat = cols >= (id_w + state_w + status_w + strat_w + sector_w + credits_w + turns_w + act_w + 12)
        want_cargo = cols >= (id_w + state_w + status_w + strat_w + sector_w + credits_w + fuel_w + org_w + equip_w + turns_w + act_w + 16)

        # Any remaining space goes to a final "NOTE" column (stable width, no jitter).
        base = id_w + state_w + sector_w + credits_w + turns_w + act_w + 7
        if want_status:
            base += status_w + 1
        if want_strat:
            base += strat_w + 1
        if want_cargo:
            base += fuel_w + org_w + equip_w + 3
        note_w = max(0, cols - base - 1)

        # Header
        out.append(_move(row, 1))
        out.append(BG_HEADER + ANSI_BOLD + FG_WHITE)
        hdr = f" {'BOT':<{id_w}}{'STATE':<{state_w}}"
        if want_status:
            hdr += f"{'STATUS':<{status_w}}"
        if want_strat:
            hdr += f"{'STRATEGY':<{strat_w}}"
        hdr += (
            f"{'SEC':>{sector_w}}"
            f"{'CR':>{credits_w}}"
        )
        if want_cargo:
            hdr += f"{'F':>{fuel_w}}{'O':>{org_w}}{'E':>{equip_w}}"
        hdr += f"{'TURNS':>{turns_w}}{'ACT':<{act_w}}"
        if note_w > 8:
            hdr += f" {'NOTE':<{note_w}}"
        out.append(hdr.ljust(cols)[:cols])
        out.append(ANSI_RESET)
        row += 1

        # Separator
        out.append(_move(row, 1) + FG_GRAY + BOX_H * cols + ANSI_RESET)
        row += 1

        # Clamp selection
        max_display = total_rows - row
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
            status_detail = (bot.get("status_detail") or "").strip()
            if not status_detail:
                status_detail = "-"
            strat = (bot.get("strategy") or "").strip()
            if not strat:
                # Prefer id(mode) if available, match web dashboard behavior.
                sid = (bot.get("strategy_id") or "").strip()
                smode = (bot.get("strategy_mode") or "").strip()
                strat = (sid + (f"({smode})" if (sid and smode) else "")) or "-"
            activity = (bot.get("activity_context") or "").strip() or state
            fuel = str(bot.get("cargo_fuel_ore", 0) or 0)
            org = str(bot.get("cargo_organics", 0) or 0)
            equip = str(bot.get("cargo_equipment", 0) or 0)
            note = (bot.get("exit_reason") or "").strip()

            line = (
                f" {_shorten(bot_id, id_w)}"
                f"{state_color}{state:<{state_w}}{ANSI_RESET}{bg}"
            )
            if want_status:
                line += f"{FG_GRAY}{_shorten(status_detail, status_w)}{ANSI_RESET}{bg}"
            if want_strat:
                line += f"{FG_WHITE}{_shorten(strat, strat_w)}{ANSI_RESET}{bg}"
            line += (
                f"{sector:>{sector_w}}"
                f"{FG_CYAN}{credits:>{credits_w}}{ANSI_RESET}{bg}"
            )
            if want_cargo:
                line += f"{fuel:>{fuel_w}}{org:>{org_w}}{equip:>{equip_w}}"
            line += f"{turns:>{turns_w}}{_shorten(activity, act_w)}"
            if note_w > 8:
                line += f" {FG_GRAY}{_shorten(note, note_w)}{ANSI_RESET}{bg}"

            out.append(_move(row, 1) + bg + line)
            # Pad to full terminal width (stops artifacts when shrinking lines).
            remaining = max(0, cols - len(line) - 1)
            if remaining:
                out.append(" " * remaining)
            out.append(ANSI_RESET)
            row += 1

        return row

    def _render_confirm(self, rows: int, cols: int) -> str:
        """Render a confirmation prompt near the bottom."""
        action = self._confirm_action or ""
        bot_id = self._confirm_bot_id or ""
        msg = f" {action.upper()} bot {bot_id}? [y/N] "
        col = max(1, (cols - len(msg)) // 2)
        return (
            _move(rows - 2, col)
            + BG_HEADER + ANSI_BOLD
            + (FG_RED if action == "kill" else FG_GREEN)
            + msg
            + ANSI_RESET
        )

    def _render_help_bar(self, cols: int) -> str:
        if self._log_viewer.active:
            keys = (
                f"{ANSI_BOLD}{FG_WHITE}ESC{ANSI_RESET}{FG_GRAY} close  "
                f"{ANSI_BOLD}{FG_WHITE}j/k{ANSI_RESET}{FG_GRAY} scroll  "
                f"{ANSI_BOLD}{FG_WHITE}G{ANSI_RESET}{FG_GRAY} bottom"
                f"{ANSI_RESET}"
            )
        else:
            keys = (
                f"{ANSI_BOLD}{FG_WHITE}q{ANSI_RESET}{FG_GRAY} quit  "
                f"{ANSI_BOLD}{FG_WHITE}j/k{ANSI_RESET}{FG_GRAY} nav  "
                f"{ANSI_BOLD}{FG_WHITE}l{ANSI_RESET}{FG_GRAY} logs  "
                f"{ANSI_BOLD}{FG_WHITE}K{ANSI_RESET}{FG_GRAY} kill  "
                f"{ANSI_BOLD}{FG_WHITE}R{ANSI_RESET}{FG_GRAY} restart  "
                f"{ANSI_BOLD}{FG_WHITE}s{ANSI_RESET}{FG_GRAY} sort:{self._sort_key}  "
                f"{ANSI_BOLD}{FG_WHITE}r{ANSI_RESET}{FG_GRAY} reverse"
                f"{ANSI_RESET}"
            )
        return BG_HEADER + keys + " " * max(cols - 80, 0) + ANSI_RESET
