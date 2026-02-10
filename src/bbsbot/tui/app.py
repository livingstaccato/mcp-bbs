from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import signal
import sys
import termios
import tty
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyte

ANSI_RESET = "\x1b[0m"
ANSI_HIDE_CURSOR = "\x1b[?25l"
ANSI_SHOW_CURSOR = "\x1b[?25h"
ANSI_ALT_SCREEN = "\x1b[?1049h"
ANSI_EXIT_ALT = "\x1b[?1049l"


def _move_to(row: int, col: int) -> str:
    return f"\x1b[{row};{col}H"


def _clear_screen() -> str:
    return "\x1b[2J"


FG_CODES = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
    "brightblack": 90,
    "brightred": 91,
    "brightgreen": 92,
    "brightyellow": 93,
    "brightblue": 94,
    "brightmagenta": 95,
    "brightcyan": 96,
    "brightwhite": 97,
}

BG_CODES = {
    "black": 40,
    "red": 41,
    "green": 42,
    "yellow": 43,
    "blue": 44,
    "magenta": 45,
    "cyan": 46,
    "white": 47,
    "brightblack": 100,
    "brightred": 101,
    "brightgreen": 102,
    "brightyellow": 103,
    "brightblue": 104,
    "brightmagenta": 105,
    "brightcyan": 106,
    "brightwhite": 107,
}


@dataclass
class SnapshotEvent:
    ts: float
    raw_bytes: bytes
    screen_hash: str = ""
    cursor: dict[str, int] = field(default_factory=dict)
    cols: int = 0
    rows: int = 0
    session_id: str = ""


@dataclass
class SessionInfo:
    session_id: str
    last_seen: float
    cursor: dict[str, int] = field(default_factory=dict)
    screen_hash: str = ""


class AnsiBuffer:
    def __init__(self, cols: int, rows: int) -> None:
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)

    def resize(self, cols: int, rows: int) -> None:
        self._screen.resize(cols, rows)

    def reset(self) -> None:
        self._screen.reset()

    def feed(self, data: bytes) -> None:
        if not data:
            return
        text = data.decode("cp437", errors="replace")
        self._stream.feed(text)

    def render_lines(self, width: int, height: int) -> list[str]:
        lines: list[str] = []
        buffer = self._screen.buffer
        for y in range(height):
            row = buffer.get(y, {})
            line_parts: list[str] = []
            last_style: tuple[str, str, bool, bool, bool, bool] | None = None
            for x in range(width):
                cell = row.get(x)
                if cell is None:
                    char = " "
                    style = ("default", "default", False, False, False, False)
                else:
                    fg = cell.fg or "default"
                    bg = cell.bg or "default"
                    bold = bool(cell.bold)
                    underscore = bool(getattr(cell, "underscore", False))
                    reverse = bool(getattr(cell, "reverse", False))
                    blink = bool(getattr(cell, "blink", False))
                    style = (fg, bg, bold, underscore, reverse, blink)
                    char = cell.data or " "

                if style != last_style:
                    line_parts.append(_style_to_sgr(*style))
                    last_style = style
                line_parts.append(char)
            line_parts.append(ANSI_RESET)
            lines.append("".join(line_parts))
        return lines


def _style_to_sgr(
    fg: str,
    bg: str,
    bold: bool,
    underscore: bool,
    reverse: bool,
    blink: bool,
) -> str:
    if reverse:
        fg, bg = bg, fg
    codes: list[int] = []
    if bold:
        codes.append(1)
    if underscore:
        codes.append(4)
    if blink:
        codes.append(5)
    if fg != "default" and fg in FG_CODES:
        codes.append(FG_CODES[fg])
    if bg != "default" and bg in BG_CODES:
        codes.append(BG_CODES[bg])
    if not codes:
        return ANSI_RESET
    return f"\x1b[{';'.join(str(c) for c in codes)}m"


class SpyTui:
    def __init__(self, host: str, port: int, log_path: str | None) -> None:
        self._host = host
        self._port = port
        self._log_path = Path(log_path) if log_path else None
        self._loop = asyncio.get_event_loop()
        self._events: list[SnapshotEvent] = []
        self._replay_index = 0
        self._replay_playing = False
        self._replay_speed = 1.0
        self._mode = "live"
        self._right_tab = "replay"
        self._live_buffer = AnsiBuffer(80, 25)
        self._replay_buffer = AnsiBuffer(80, 25)
        self._sessions: dict[str, SessionInfo] = {}
        self._current_session_id: str | None = None
        self._metadata: dict[str, Any] = {}
        self._dirty = True
        self._stop = False
        self._stdin_fd = sys.stdin.fileno()
        self._orig_term = termios.tcgetattr(self._stdin_fd)

    async def run(self) -> None:
        self._install_terminal()
        try:
            if self._log_path:
                self._load_replay()
            await self._main()
        finally:
            self._restore_terminal()

    def _install_terminal(self) -> None:
        tty.setcbreak(self._stdin_fd)
        sys.stdout.write(ANSI_ALT_SCREEN + ANSI_HIDE_CURSOR)
        sys.stdout.flush()

    def _restore_terminal(self) -> None:
        termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._orig_term)
        sys.stdout.write(ANSI_SHOW_CURSOR + ANSI_EXIT_ALT)
        sys.stdout.flush()

    async def _main(self) -> None:
        self._loop.add_reader(self._stdin_fd, self._on_keypress)
        signal.signal(signal.SIGWINCH, lambda *_: self._mark_dirty())
        live_task = self._loop.create_task(self._connect_live())
        try:
            while not self._stop:
                await asyncio.sleep(0.05)
                if self._replay_playing and self._mode == "replay":
                    await self._advance_replay()
                if self._dirty:
                    self._render()
        finally:
            live_task.cancel()
            with contextlib.suppress(Exception):
                await live_task

    async def _connect_live(self) -> None:
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if payload.get("event") != "snapshot":
                    continue
                data = payload.get("data", {})
                raw_b64 = data.get("raw_bytes_b64", "")
                raw = base64.b64decode(raw_b64) if raw_b64 else b""
                self._live_buffer.feed(raw)
                event = SnapshotEvent(
                    ts=float(data.get("captured_at") or 0.0),
                    raw_bytes=raw,
                    screen_hash=str(data.get("screen_hash", "")),
                    cursor=data.get("cursor", {}) or {},
                    cols=int(data.get("cols", 0) or 0),
                    rows=int(data.get("rows", 0) or 0),
                    session_id=str(data.get("session_id", "")),
                )
                if event.session_id:
                    self._current_session_id = event.session_id
                    self._sessions[event.session_id] = SessionInfo(
                        session_id=event.session_id,
                        last_seen=event.ts,
                        cursor=event.cursor,
                        screen_hash=event.screen_hash,
                    )
                self._metadata = {
                    "session_id": event.session_id,
                    "screen_hash": event.screen_hash,
                    "cursor": event.cursor,
                    "captured_at": event.ts,
                    "cols": event.cols,
                    "rows": event.rows,
                    "prompt_detected": data.get("prompt_detected"),
                }
                self._dirty = True
        finally:
            writer.close()
            await writer.wait_closed()

    def _load_replay(self) -> None:
        if not self._log_path or not self._log_path.exists():
            return
        self._events = []
        for line in self._log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("event") != "read":
                continue
            data = record.get("data", {})
            raw_b64 = data.get("raw_bytes_b64", "")
            raw = base64.b64decode(raw_b64) if raw_b64 else b""
            self._events.append(
                SnapshotEvent(
                    ts=float(record.get("ts", 0.0)),
                    raw_bytes=raw,
                    screen_hash=str(data.get("screen_hash", "")),
                    cursor=data.get("cursor", {}) or {},
                    cols=int(data.get("cols", 0) or 0),
                    rows=int(data.get("rows", 0) or 0),
                    session_id=str(record.get("session_id", "")),
                )
            )
        self._replay_index = 0
        self._replay_buffer.reset()

    async def _advance_replay(self) -> None:
        if not self._events:
            return
        next_index = self._replay_index + 1
        if next_index >= len(self._events):
            self._replay_playing = False
            return
        prev = self._events[self._replay_index]
        nxt = self._events[next_index]
        delta = (nxt.ts - prev.ts) / max(self._replay_speed, 0.01)
        if delta > 0:
            await asyncio.sleep(delta)
        self._apply_replay_index(next_index)

    def _apply_replay_index(self, index: int) -> None:
        index = max(0, min(index, max(len(self._events) - 1, 0)))
        if index < self._replay_index:
            self._replay_buffer.reset()
            for i in range(index + 1):
                self._replay_buffer.feed(self._events[i].raw_bytes)
        else:
            for i in range(self._replay_index + 1, index + 1):
                self._replay_buffer.feed(self._events[i].raw_bytes)
        self._replay_index = index
        self._dirty = True

    def _on_keypress(self) -> None:
        ch = os.read(self._stdin_fd, 1)
        if not ch:
            return
        key = ch.decode(errors="ignore")
        if key == "q":
            self._stop = True
            return
        if key == "\t":
            self._right_tab = "sessions" if self._right_tab == "replay" else "replay"
        elif key == "l":
            self._mode = "live"
        elif key == "r":
            self._mode = "replay"
        elif key == " " and self._mode == "replay":
            self._replay_playing = not self._replay_playing
        elif key == "[" and self._mode == "replay":
            self._apply_replay_index(self._replay_index - 1)
        elif key == "]" and self._mode == "replay":
            self._apply_replay_index(self._replay_index + 1)
        elif key == "+" and self._mode == "replay":
            self._replay_speed = min(self._replay_speed + 0.25, 8.0)
        elif key == "-" and self._mode == "replay":
            self._replay_speed = max(self._replay_speed - 0.25, 0.25)
        elif key in "0123456789" and self._mode == "replay":
            if self._events:
                n = int(key)
                target = int(round((n / 9) * (len(self._events) - 1)))
                self._apply_replay_index(target)
        elif key == "g" and self._mode == "replay":
            self._apply_replay_index(0)
        elif key == "G" and self._mode == "replay" and self._events:
            self._apply_replay_index(len(self._events) - 1)
        self._dirty = True

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _render(self) -> None:
        self._dirty = False
        cols, rows = os.get_terminal_size()
        top_bar = 1
        meta_rows = 2
        usable_rows = max(rows - top_bar - meta_rows - 1, 1)
        left_width = min(80, max(cols - 30, 20))
        right_width = max(cols - left_width - 3, 20)
        left_height = usable_rows
        right_height = usable_rows

        output: list[str] = []
        output.append(_clear_screen())
        output.append(_move_to(1, 1))
        output.append(self._render_top_bar(cols))

        start_row = 2
        left_col = 1
        right_col = left_col + left_width + 2

        output.extend(self._render_left_pane(start_row, left_col, left_width, left_height))
        output.extend(self._render_right_pane(start_row, right_col, right_width, right_height))

        meta_row = top_bar + left_height + 2
        output.extend(self._render_metadata(meta_row, cols))

        sys.stdout.write("".join(output))
        sys.stdout.flush()

    def _render_top_bar(self, width: int) -> str:
        mode = self._mode.upper()
        tab = "Replay" if self._right_tab == "replay" else "Sessions"
        left = f"bbsbot spy  mode:{mode}  right:{tab}"
        right = f"{self._host}:{self._port}"
        text = f"{left}  {right}"
        return text[:width].ljust(width)

    def _render_left_pane(self, row: int, col: int, width: int, height: int) -> list[str]:
        buffer = self._live_buffer if self._mode == "live" else self._replay_buffer
        lines = buffer.render_lines(width, height)
        output: list[str] = []
        for i, line in enumerate(lines):
            output.append(_move_to(row + i, col))
            output.append(line[:width])
        return output

    def _render_right_pane(self, row: int, col: int, width: int, height: int) -> list[str]:
        if self._right_tab == "sessions":
            return self._render_sessions(row, col, width, height)
        return self._render_replay_controls(row, col, width, height)

    def _render_replay_controls(self, row: int, col: int, width: int, height: int) -> list[str]:
        lines = [
            "REPLAY",
            f"playing: {'yes' if self._replay_playing else 'no'}",
            f"speed: {self._replay_speed:.2f}x",
            f"index: {self._replay_index}/{max(len(self._events) - 1, 0)}",
            "keys: space play/pause",
            "[ / ] step",
            "+ / - speed",
            "0-9 jump, g/G ends",
            "tab switch pane",
        ]
        return self._render_boxed_lines(row, col, width, height, lines)

    def _render_sessions(self, row: int, col: int, width: int, height: int) -> list[str]:
        lines = ["SESSIONS"]
        for idx, info in enumerate(sorted(self._sessions.values(), key=lambda s: s.last_seen, reverse=True), 1):
            if len(lines) >= height - 1:
                break
            line = f"{idx:>2} {info.session_id[:6]} cur:{info.cursor.get('x', 0)},{info.cursor.get('y', 0)}"
            lines.append(line)
        if not self._sessions:
            lines.append("(no sessions)")
        return self._render_boxed_lines(row, col, width, height, lines)

    def _render_boxed_lines(self, row: int, col: int, width: int, height: int, lines: list[str]) -> list[str]:
        output: list[str] = []
        box_top = "+" + "-" * (width - 2) + "+"
        box_bottom = box_top
        output.append(_move_to(row, col))
        output.append(box_top)
        for i in range(1, height - 1):
            content = lines[i - 1] if i - 1 < len(lines) else ""
            content = content[: width - 2].ljust(width - 2)
            output.append(_move_to(row + i, col))
            output.append(f"|{content}|")
        if height > 1:
            output.append(_move_to(row + height - 1, col))
            output.append(box_bottom)
        return output

    def _render_metadata(self, row: int, width: int) -> list[str]:
        session_id = self._metadata.get("session_id", "")
        cursor = self._metadata.get("cursor", {}) or {}
        screen_hash = self._metadata.get("screen_hash", "")
        cols = self._metadata.get("cols", "")
        rows = self._metadata.get("rows", "")
        prompt = self._metadata.get("prompt_detected") or {}
        prompt_id = prompt.get("prompt_id", "")
        input_type = prompt.get("input_type", "")
        line1 = (
            f"session:{session_id} prompt:{prompt_id} input:{input_type} "
            f"cursor:{cursor.get('x', 0)},{cursor.get('y', 0)}"
        )
        line2 = f"hash:{screen_hash} size:{cols}x{rows}"
        return [
            _move_to(row, 1) + line1[:width].ljust(width),
            _move_to(row + 1, 1) + line2[:width].ljust(width),
        ]


async def run_tui(host: str, port: int, log_path: str | None) -> None:
    app = SpyTui(host=host, port=port, log_path=log_path)
    await app.run()
