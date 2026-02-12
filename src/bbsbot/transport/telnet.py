# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Telnet transport implementation with proper protocol handling."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

import structlog

from bbsbot.transport.base import ConnectionTransport

if TYPE_CHECKING:
    from asyncio import StreamReader, StreamWriter

log = structlog.get_logger()

# Telnet protocol constants
IAC = 255  # Interpret As Command
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250  # Subnegotiation Begin
SE = 240  # Subnegotiation End

# Telnet options
OPT_BINARY = 0
OPT_ECHO = 1
OPT_SGA = 3  # Suppress Go Ahead
OPT_TTYPE = 24  # Terminal Type
OPT_NAWS = 31  # Negotiate About Window Size

# Terminal type subnegotiation
TTYPE_IS = 0

# Connection timeout
DEFAULT_CONNECT_TIMEOUT_S = 30.0


class TelnetTransport(ConnectionTransport):
    """Telnet protocol transport implementation."""

    def __init__(self) -> None:
        """Initialize telnet transport."""
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None
        self._negotiated: dict[str, set[int]] = {
            "do": set(),
            "dont": set(),
            "will": set(),
            "wont": set(),
        }
        self._rx_buf = bytearray()
        self._cols: int = 80
        self._rows: int = 25
        self._term: str = "ANSI"

    async def connect(
        self,
        host: str,
        port: int,
        cols: int = 80,
        rows: int = 25,
        term: str = "ANSI",
        timeout: float = DEFAULT_CONNECT_TIMEOUT_S,
        **kwargs: Any,
    ) -> None:
        """Establish telnet connection to remote host.

        Args:
            host: Remote hostname or IP address
            port: Remote port number
            cols: Terminal columns for NAWS
            rows: Terminal rows for NAWS
            term: Terminal type (e.g., "ANSI", "VT100")
            timeout: Connection timeout in seconds
            **kwargs: Unused, for compatibility

        Raises:
            ConnectionError: If connection fails
            asyncio.TimeoutError: If connection times out
        """
        if self._writer:
            await self.disconnect()

        try:
            self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {host}:{port}") from e

        self._cols = cols
        self._rows = rows
        self._term = term

        # Send initial WILL commands to announce client capabilities
        # This matches standard telnet client behavior that BBSes expect
        await self._send_will(OPT_BINARY)
        await self._send_will(OPT_SGA)

        log.info("telnet_connected", host=host, port=port, cols=cols, rows=rows, term=term)

    async def disconnect(self) -> None:
        """Close connection and cleanup resources."""
        if not self._writer:
            return

        try:
            self._writer.close()
            await self._writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError, RuntimeError):
            pass
        finally:
            self._writer = None
            self._reader = None
            self._rx_buf.clear()
            self._negotiated = {
                "do": set(),
                "dont": set(),
                "will": set(),
                "wont": set(),
            }

        log.info("telnet_disconnected")

    async def send(self, data: bytes) -> None:
        """Send raw bytes with IAC escaping per RFC 854.

        CRITICAL FIX: Escape IAC bytes (0xFF) by doubling them to prevent
        data corruption when sending binary data over telnet.

        Args:
            data: Raw bytes to send

        Raises:
            ConnectionError: If not connected or send fails
        """
        if not self._writer:
            raise ConnectionError("Not connected")

        # Escape IAC bytes per RFC 854: 0xFF → 0xFF 0xFF
        escaped = data.replace(b"\xff", b"\xff\xff")

        try:
            self._writer.write(escaped)
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            await self.disconnect()
            raise ConnectionError("Send failed") from e

    async def receive(self, max_bytes: int, timeout_ms: int) -> bytes:
        """Receive raw bytes from connection.

        Args:
            max_bytes: Maximum bytes to read
            timeout_ms: Read timeout in milliseconds

        Returns:
            Bytes read from connection (may be empty on timeout)

        Raises:
            ConnectionError: If not connected or connection lost
        """
        if not self._reader:
            raise ConnectionError("Not connected")

        try:
            chunk = await asyncio.wait_for(self._reader.read(max_bytes), timeout=timeout_ms / 1000)
        except TimeoutError:
            return b""
        except (ConnectionResetError, BrokenPipeError) as e:
            await self.disconnect()
            raise ConnectionError("Connection lost") from e

        if not chunk:
            await self.disconnect()
            raise ConnectionError("Connection closed by remote")

        # Buffer and process telnet protocol
        self._rx_buf.extend(chunk)
        data = bytes(self._rx_buf)
        self._rx_buf.clear()

        return self._handle_telnet(data)

    def is_connected(self) -> bool:
        """Check if connection is active.

        Returns:
            True if connected, False otherwise
        """
        return self._writer is not None and not self._writer.is_closing()

    async def set_size(self, cols: int, rows: int) -> None:
        """Update terminal size and send NAWS.

        Args:
            cols: New terminal columns
            rows: New terminal rows

        Raises:
            ConnectionError: If not connected
        """
        if not self._writer:
            raise ConnectionError("Not connected")

        self._cols = cols
        self._rows = rows
        await self._send_naws(cols, rows)

    def _handle_telnet(self, data: bytes) -> bytes:
        """Process telnet protocol commands and return clean data.

        Args:
            data: Raw data with telnet commands

        Returns:
            Data with telnet commands processed and removed
        """
        i = 0
        while i < len(data):
            if data[i] == IAC and i + 1 < len(data):
                cmd = data[i + 1]
                # Handle DO/DONT/WILL/WONT commands
                if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                    asyncio.create_task(self._negotiate(cmd, data[i + 2]))
                    i += 3
                    continue
                # Handle subnegotiation
                elif cmd == SB and (end := data.find(bytes([IAC, SE]), i + 2)) != -1:
                    asyncio.create_task(self._handle_subnegotiation(data[i + 2 : end]))
                    i = end + 2
                    continue
            i += 1

        return self._strip_telnet_commands(data)

    async def _negotiate(self, cmd: int, opt: int) -> None:
        """Handle telnet option negotiation.

        Args:
            cmd: Negotiation command (DO/DONT/WILL/WONT)
            opt: Option code
        """
        if not self._writer:
            return

        # Track negotiated options
        if cmd == DO:
            self._negotiated["do"].add(opt)
        elif cmd == DONT:
            self._negotiated["dont"].add(opt)
        elif cmd == WILL:
            self._negotiated["will"].add(opt)
        elif cmd == WONT:
            self._negotiated["wont"].add(opt)

        try:
            if cmd == DO:
                # Server asks us to enable an option
                if opt in (OPT_BINARY, OPT_SGA):
                    await self._send_will(opt)
                    return
                if opt == OPT_NAWS:
                    await self._send_will(opt)
                    await self._send_naws(self._cols, self._rows)
                    return
                if opt == OPT_TTYPE:
                    await self._send_will(opt)
                    await self._send_ttype(self._term)
                    return
                await self._send_wont(opt)
                return

            if cmd == DONT:
                await self._send_wont(opt)
                return

            if cmd == WILL:
                # Server announces it will enable an option
                if opt in (OPT_ECHO, OPT_SGA, OPT_BINARY):
                    await self._send_do(opt)
                    return
                await self._send_dont(opt)
                return

            if cmd == WONT:
                await self._send_dont(opt)
        except (ConnectionResetError, BrokenPipeError):
            pass

    async def _handle_subnegotiation(self, sub: bytes) -> None:
        """Handle telnet subnegotiation.

        Args:
            sub: Subnegotiation payload
        """
        if not sub or not self._writer:
            return

        # Handle TTYPE SEND request
        if sub[0] == OPT_TTYPE and len(sub) > 1 and sub[1] == 1:
            await self._send_ttype(self._term)

    def _strip_telnet_commands(self, data: bytes) -> bytes:
        """Strip telnet IAC commands from data stream.

        Args:
            data: Raw bytes from telnet connection

        Returns:
            Data with telnet commands removed
        """
        result = bytearray()
        i = 0
        while i < len(data):
            if data[i] == IAC and i + 1 < len(data):
                cmd = data[i + 1]
                if cmd in (DO, DONT, WILL, WONT):
                    if i + 2 < len(data):
                        i += 3  # Skip IAC + cmd + option
                        continue
                elif cmd == SB:
                    # Find SE
                    j = i + 2
                    while j < len(data) - 1:
                        if data[j] == IAC and data[j + 1] == SE:
                            i = j + 2
                            break
                        j += 1
                    else:
                        i = len(data)
                    continue
                elif cmd == IAC:
                    # Escaped IAC (0xFF 0xFF) → single 0xFF
                    result.append(IAC)
                    i += 2
                    continue
            result.append(data[i])
            i += 1
        return bytes(result)

    async def _send_cmd(self, cmd: int, opt: int) -> None:
        """Send a telnet command.

        Args:
            cmd: Command byte
            opt: Option byte
        """
        if not self._writer or self._writer.is_closing():
            return

        self._writer.write(bytes([IAC, cmd, opt]))
        with contextlib.suppress(ConnectionResetError, BrokenPipeError):
            await self._writer.drain()

    async def _send_will(self, opt: int) -> None:
        """Send WILL command for option."""
        if opt not in self._negotiated["will"]:
            await self._send_cmd(WILL, opt)
            self._negotiated["will"].add(opt)

    async def _send_wont(self, opt: int) -> None:
        """Send WONT command for option."""
        if opt not in self._negotiated["wont"]:
            await self._send_cmd(WONT, opt)
            self._negotiated["wont"].add(opt)

    async def _send_do(self, opt: int) -> None:
        """Send DO command for option."""
        if opt not in self._negotiated["do"]:
            await self._send_cmd(DO, opt)
            self._negotiated["do"].add(opt)

    async def _send_dont(self, opt: int) -> None:
        """Send DONT command for option."""
        if opt not in self._negotiated["dont"]:
            await self._send_cmd(DONT, opt)
            self._negotiated["dont"].add(opt)

    async def _send_naws(self, cols: int, rows: int) -> None:
        """Send NAWS (Negotiate About Window Size) subnegotiation."""
        width_high = (cols >> 8) & 0xFF
        width_low = cols & 0xFF
        height_high = (rows >> 8) & 0xFF
        height_low = rows & 0xFF
        msg = bytes([IAC, SB, OPT_NAWS, width_high, width_low, height_high, height_low, IAC, SE])

        if not self._writer or self._writer.is_closing():
            return

        self._writer.write(msg)
        with contextlib.suppress(ConnectionResetError, BrokenPipeError):
            await self._writer.drain()

    async def _send_ttype(self, term: str) -> None:
        """Send terminal type subnegotiation."""
        payload = bytes([OPT_TTYPE, TTYPE_IS]) + term.encode("ascii", errors="replace")
        await self._send_subnegotiation(payload)

    async def _send_subnegotiation(self, payload: bytes) -> None:
        """Send a telnet subnegotiation."""
        if not self._writer or self._writer.is_closing():
            return

        self._writer.write(bytes([IAC, SB]) + payload + bytes([IAC, SE]))
        with contextlib.suppress(ConnectionResetError, BrokenPipeError):
            await self._writer.drain()
