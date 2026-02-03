"""Individual BBS session state management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from mcp_bbs.constants import CP437
from mcp_bbs.learning.engine import LearningEngine
from mcp_bbs.logging.session_logger import SessionLogger
from mcp_bbs.terminal.emulator import TerminalEmulator
from mcp_bbs.transport.base import ConnectionTransport


@dataclass
class Session:
    """Represents a single BBS session with isolated state."""

    session_id: str
    session_number: int
    transport: ConnectionTransport
    emulator: TerminalEmulator
    host: str
    port: int
    logger: SessionLogger | None = None
    learning: LearningEngine | None = None

    # State protection
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, keys: str) -> None:
        """Send keystrokes with CP437 encoding.

        Args:
            keys: Keystrokes to send (may include escape sequences)

        Raises:
            ConnectionError: If transport send fails
        """
        async with self._lock:
            payload = keys.encode(CP437, errors="replace")
            await self.transport.send(payload)
            if self.logger:
                await self.logger.log_send(keys)

    async def read(self, timeout_ms: int, max_bytes: int) -> dict:
        """Read from transport, update emulator, return snapshot.

        Args:
            timeout_ms: Read timeout in milliseconds
            max_bytes: Maximum bytes to read

        Returns:
            Screen snapshot dictionary

        Raises:
            ConnectionError: If transport is disconnected
        """
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

            # Log and learn
            if self.logger:
                await self.logger.log_screen(snapshot, raw)
            if self.learning:
                await self.learning.process_screen(snapshot)

            return snapshot

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
                await self.transport.set_size(cols, rows)  # type: ignore
            if self.logger:
                await self.logger.log_event("resize", {"cols": cols, "rows": rows})

    async def disconnect(self) -> None:
        """Disconnect transport and cleanup resources."""
        async with self._lock:
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

    def get_status(self) -> dict:
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
        }
