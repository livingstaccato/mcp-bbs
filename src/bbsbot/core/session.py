"""Individual BBS session state management."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr

from collections.abc import Callable

from bbsbot.addons.manager import AddonManager
from bbsbot.constants import CP437
from bbsbot.keepalive import KeepaliveController
from bbsbot.learning.engine import LearningEngine
from bbsbot.logging.session_logger import SessionLogger
from bbsbot.terminal.emulator import TerminalEmulator
from bbsbot.transport.base import ConnectionTransport


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

    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    _awaiting_read: bool = PrivateAttr(default=False)
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
                positional = [
                    p
                    for p in params
                    if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                ]
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
        printable = keys.replace("\r", "\\r").replace("\n", "\\n")
        print(
            f"status action=send host={self.host} port={self.port} keys={printable}"
        )
        async with self._lock:
            payload = keys.encode(CP437, errors="replace")
            await self.transport.send(payload)
            if self.logger:
                await self.logger.log_send(keys)
            if mark_awaiting:
                self._awaiting_read = True

    async def read(self, timeout_ms: int, max_bytes: int) -> dict[str, Any]:
        """Read from transport, update emulator, return snapshot with detection.

        Args:
            timeout_ms: Read timeout in milliseconds
            max_bytes: Maximum bytes to read

        Returns:
            Screen snapshot dictionary with optional prompt_detected field

        Raises:
            ConnectionError: If transport is disconnected
        """
        print(
            f"status action=read host={self.host} port={self.port} timeout_ms={timeout_ms} max_bytes={max_bytes}"
        )
        async with self._lock:
            try:
                raw = await self.transport.receive(max_bytes, timeout_ms)
            except ConnectionError:
                # Return disconnected snapshot
                return {
                    "screen": "",
                    "screen_hash": "",
                    "cursor": {"x": 0, "y": 0},
                    "cols": self.emulator.cols,
                    "rows": self.emulator.rows,
                    "term": self.emulator.term,
                    "disconnected": True,
                }

            # Process data through emulator
            if raw:
                self.emulator.process(raw)

            snapshot = self.emulator.get_snapshot()

            # Log
            if self.logger:
                await self.logger.log_screen(snapshot, raw)

            # Learning with prompt detection
            prompt_detection = None
            if self.learning:
                prompt_detection = await self.learning.process_screen(snapshot)

            # Add detection metadata to snapshot
            if prompt_detection:
                snapshot["prompt_detected"] = {
                    "prompt_id": prompt_detection.prompt_id,
                    "input_type": prompt_detection.input_type,
                    "is_idle": prompt_detection.is_idle,
                    "kv_data": prompt_detection.kv_data,
                }

            if self.addons and self.logger:
                for event in self.addons.process(snapshot):
                    await self.logger.log_event(event.name, event.data)

            # Clear send gate after any read attempt
            self._awaiting_read = False

            self._emit_watch(snapshot, raw)

            return snapshot

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
        async with self._lock:
            self.emulator.resize(cols, rows)
            # Update transport if it supports size changes (telnet does)
            if hasattr(self.transport, "set_size"):
                await self.transport.set_size(cols, rows)
            if self.logger:
                await self.logger.log_event("resize", {"cols": cols, "rows": rows})

    async def disconnect(self) -> None:
        """Disconnect transport and cleanup resources."""
        async with self._lock:
            # Stop keepalive first
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
