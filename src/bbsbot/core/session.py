# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Individual BBS session state management."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr

from bbsbot.addons.manager import AddonManager
from bbsbot.constants import CP437
from bbsbot.keepalive import KeepaliveController
from bbsbot.learning.engine import LearningEngine
from bbsbot.logging import get_logger
from bbsbot.logging.session_logger import SessionLogger
from bbsbot.terminal.emulator import TerminalEmulator
from bbsbot.transport.base import ConnectionTransport

logger = get_logger(__name__)


class Session(BaseModel):
    """Represents a single BBS session with isolated state."""

    session_id: str
    session_number: int
    transport: ConnectionTransport
    emulator: TerminalEmulator
    host: str
    port: int
    logger: SessionLogger | None = None
    learning: LearningEngine | None = None
    addons: AddonManager | None = None

    keepalive: KeepaliveController | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _send_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    _awaiting_read: bool = PrivateAttr(default=False)

    # Event-driven reader pump (end-state: one task blocks on network I/O).
    _reader_task: asyncio.Task[None] | None = PrivateAttr(default=None)
    _update_cond: asyncio.Condition = PrivateAttr(default_factory=asyncio.Condition)
    _update_seq: int = PrivateAttr(default=0)
    _screen_change_seq: int = PrivateAttr(default=0)
    _disconnected: bool = PrivateAttr(default=False)
    _last_screen_hash: str = PrivateAttr(default="")
    _last_screen_change_mono: float = PrivateAttr(default=0.0)
    _latest_prompt_detected: dict[str, Any] | None = PrivateAttr(default=None)

    @dataclass
    class _WatchEntry:
        callback: Callable[..., None]
        interval_s: float
        last_ts: float
        arity: int

    _watchers: list[_WatchEntry] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        """Initialize keepalive controller after model fields are set."""

        # Wrapper for keepalive that matches expected signature
        async def _send_with_result(keys: str) -> str:
            await self.send(keys, mark_awaiting=False)
            return "ok"

        if self.keepalive is None:
            self.keepalive = KeepaliveController(
                send_cb=_send_with_result,
                is_connected=self.is_connected,
            )
        # Start keepalive if connected
        if self.is_connected():
            self.keepalive.on_connect()

    def start_reader(self, *, max_bytes: int = 8192, timeout_ms: int = 60000) -> None:
        """Start background reader pump.

        End-state: all transport reads happen here; callers await update events.
        """
        if self._reader_task is not None and not self._reader_task.done():
            return
        if not self.is_connected():
            self._disconnected = True
            return
        self._disconnected = False
        self._reader_task = asyncio.create_task(self._reader_loop(max_bytes=max_bytes, timeout_ms=timeout_ms))

    async def stop_reader(self) -> None:
        task = self._reader_task
        self._reader_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    async def _reader_loop(self, *, max_bytes: int, timeout_ms: int) -> None:
        try:
            while self.is_connected():
                try:
                    raw = await self.transport.receive(max_bytes=max_bytes, timeout_ms=timeout_ms)
                except ConnectionError:
                    self._disconnected = True
                    async with self._update_cond:
                        self._update_cond.notify_all()
                    return
                except asyncio.CancelledError:
                    return
                except Exception:
                    # Avoid spinning on unexpected errors.
                    await asyncio.sleep(0.1)
                    continue

                if not raw:
                    continue

                prev_hash = self._last_screen_hash

                # Update emulator state and compute snapshot.
                self.emulator.process(raw)
                snapshot = self.emulator.get_snapshot()

                screen_hash = snapshot.get("screen_hash", "") or ""
                screen_changed = False
                if screen_hash and screen_hash != prev_hash:
                    self._last_screen_hash = screen_hash
                    self._last_screen_change_mono = time.monotonic()
                    screen_changed = True

                # Prompt detection runs once per update.
                prompt_detected: dict[str, Any] | None = None
                if self.learning:
                    try:
                        prompt_detection = await self.learning.process_screen(snapshot)
                    except Exception:
                        prompt_detection = None
                    if prompt_detection:
                        prompt_detected = {
                            "prompt_id": prompt_detection.prompt_id,
                            "input_type": prompt_detection.input_type,
                            "is_idle": prompt_detection.is_idle,
                            "kv_data": prompt_detection.kv_data,
                        }

                if prompt_detected:
                    snapshot["prompt_detected"] = prompt_detected
                else:
                    snapshot.pop("prompt_detected", None)
                self._latest_prompt_detected = prompt_detected

                # Clear send gate on actual receive.
                self._awaiting_read = False

                # Best-effort logging and addons.
                if self.logger:
                    with contextlib.suppress(Exception):
                        await self.logger.log_screen(snapshot, raw)
                if self.addons and self.logger:
                    try:
                        for event in self.addons.process(snapshot):
                            await self.logger.log_event(event.name, event.data)
                    except Exception:
                        pass

                # Watchers must stay non-blocking (spawn tasks, push to queues, etc.).
                self._emit_watch(snapshot, raw)

                async with self._update_cond:
                    self._update_seq += 1
                    if screen_changed:
                        self._screen_change_seq += 1
                    self._update_cond.notify_all()
        except asyncio.CancelledError:
            return

    def snapshot(self) -> dict[str, Any]:
        """Return snapshot without performing any network I/O."""
        if self._disconnected or not self.is_connected():
            return {
                "screen": "",
                "screen_hash": "",
                "cursor": {"x": 0, "y": 0},
                "cols": self.emulator.cols,
                "rows": self.emulator.rows,
                "term": self.emulator.term,
                "disconnected": True,
            }
        snap = self.emulator.get_snapshot()
        if self._latest_prompt_detected:
            snap["prompt_detected"] = dict(self._latest_prompt_detected)
            snap["prompt_detected"]["is_idle"] = self.is_idle()
        return snap

    async def rescan_prompt(self) -> None:
        """Re-run prompt detection on the current screen.

        Useful after enabling learning on a session that already has data,
        since the reader loop only runs detection when new data arrives.
        """
        if not self.learning:
            logger.debug("rescan_prompt: no learning engine, skipping")
            return
        snapshot = self.emulator.get_snapshot()
        try:
            prompt_detection = await self.learning.process_screen(snapshot)
        except Exception:
            logger.exception("rescan_prompt: detection failed")
            prompt_detection = None
        if prompt_detection:
            logger.debug("rescan_prompt: detected %s", prompt_detection.prompt_id)
            self._latest_prompt_detected = {
                "prompt_id": prompt_detection.prompt_id,
                "input_type": prompt_detection.input_type,
                "is_idle": prompt_detection.is_idle,
                "kv_data": prompt_detection.kv_data,
            }
            async with self._update_cond:
                self._update_cond.notify_all()

    def is_idle(self, threshold_s: float = 2.0) -> bool:
        if not self._last_screen_change_mono:
            return False
        return (time.monotonic() - self._last_screen_change_mono) >= threshold_s

    def seconds_until_idle(self, threshold_s: float = 2.0) -> float:
        """Return seconds until the screen is considered idle, based on last screen change."""
        if not self._last_screen_change_mono:
            return threshold_s
        elapsed = time.monotonic() - self._last_screen_change_mono
        return max(0.0, threshold_s - elapsed)

    def update_seq(self) -> int:
        return self._update_seq

    def screen_change_seq(self) -> int:
        return self._screen_change_seq

    async def wait_for_update(self, *, timeout_ms: int, since: int | None = None) -> bool:
        if self._disconnected or not self.is_connected():
            return False
        if since is None:
            since = self._update_seq
        timeout_s = max(0.0, timeout_ms / 1000.0)
        try:
            async with self._update_cond:
                await asyncio.wait_for(
                    self._update_cond.wait_for(lambda: self._update_seq > since or self._disconnected),
                    timeout=timeout_s,
                )
            return not self._disconnected and self._update_seq > since
        except TimeoutError:
            return False

    async def wait_for_screen_change(self, *, timeout_ms: int, since: int | None = None) -> bool:
        if self._disconnected or not self.is_connected():
            return False
        if since is None:
            since = self._screen_change_seq
        timeout_s = max(0.0, timeout_ms / 1000.0)
        try:
            async with self._update_cond:
                await asyncio.wait_for(
                    self._update_cond.wait_for(lambda: self._screen_change_seq > since or self._disconnected),
                    timeout=timeout_s,
                )
            return not self._disconnected and self._screen_change_seq > since
        except TimeoutError:
            return False

    async def read(self, timeout_ms: int, max_bytes: int = 8192) -> dict[str, Any]:
        """Event-driven read helper.

        End-state behavior: does NOT perform transport I/O. It waits for the
        reader pump to observe bytes (up to timeout) and returns `snapshot()`.
        """
        _ = max_bytes  # kept for call-site convenience; reader pump owns max_bytes.
        await self.wait_for_update(timeout_ms=timeout_ms)
        return self.snapshot()

    def set_watch(self, callback: Callable[..., None] | None, interval_s: float = 0.0) -> None:
        """Attach a screen watcher callback to every read (replaces existing watchers)."""
        self._watchers = []
        if callback is not None:
            self.add_watch(callback, interval_s=interval_s)

    def add_watch(self, callback: Callable[..., None], interval_s: float = 0.0) -> None:
        """Add a screen watcher callback without replacing existing watchers."""
        arity = 1
        try:
            sig = inspect.signature(callback)
            params = list(sig.parameters.values())
            if any(p.kind == p.VAR_POSITIONAL for p in params):
                arity = 2
            else:
                positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
                if len(positional) >= 2:
                    arity = 2
        except (TypeError, ValueError):
            arity = 1

        self._watchers.append(
            Session._WatchEntry(
                callback=callback,
                interval_s=max(interval_s, 0.0),
                last_ts=0.0,
                arity=arity,
            )
        )

    async def send(self, keys: str, *, mark_awaiting: bool = True) -> None:
        """Send keystrokes with CP437 encoding.

        Args:
            keys: Keystrokes to send (may include escape sequences)

        Raises:
            ConnectionError: If transport send fails
        """
        logger.debug("session_send", host=self.host, port=self.port, keys=repr(keys))
        async with self._send_lock:
            payload = keys.encode(CP437, errors="replace")
            await self.transport.send(payload)
            if self.logger:
                await self.logger.log_send(keys)
            if mark_awaiting:
                self._awaiting_read = True
            # No prompt-detection cache at Session layer.

    def _emit_watch(self, snapshot: dict[str, Any], raw: bytes) -> None:
        if not self._watchers:
            return
        now = time.monotonic()
        for watcher in self._watchers:
            try:
                if watcher.interval_s > 0 and now - watcher.last_ts < watcher.interval_s:
                    continue
                watcher.last_ts = now
                if watcher.arity >= 2:
                    watcher.callback(snapshot, raw)
                else:
                    watcher.callback(snapshot)
            except Exception:
                continue

    def get_screen(self) -> str:
        """Return current emulator screen content without any I/O wait."""
        return self.snapshot().get("screen", "")

    def is_awaiting_read(self) -> bool:
        """Return True if a send occurred without a subsequent read."""
        return self._awaiting_read

    async def set_size(self, cols: int, rows: int) -> None:
        """Update terminal size.

        Args:
            cols: New terminal columns
            rows: New terminal rows

        Raises:
            ConnectionError: If transport operation fails
        """
        self.emulator.resize(cols, rows)
        if hasattr(self.transport, "set_size"):
            await self.transport.set_size(cols, rows)
        if self.logger:
            await self.logger.log_event("resize", {"cols": cols, "rows": rows})

    async def disconnect(self) -> None:
        """Disconnect transport and cleanup resources."""
        await self.stop_reader()
        self._disconnected = True
        async with self._update_cond:
            self._update_cond.notify_all()

        await self.keepalive.on_disconnect()
        if self.logger:
            await self.logger.log_event("disconnect", {"reason": "client_disconnect"})
            await self.logger.stop()
        await self.transport.disconnect()

    def is_connected(self) -> bool:
        """Check if session is connected.

        Returns:
            True if transport is connected, False otherwise
        """
        return self.transport.is_connected()

    def get_status(self) -> dict[str, Any]:
        """Get session status.

        Returns:
            Status dictionary with connection info
        """
        return {
            "session_id": self.session_id,
            "session_number": self.session_number,
            "connected": self.is_connected(),
            "host": self.host,
            "port": self.port,
            "cols": self.emulator.cols,
            "rows": self.emulator.rows,
            "term": self.emulator.term,
            "keepalive": self.keepalive.status(),
        }
