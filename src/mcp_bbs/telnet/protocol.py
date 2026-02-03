"""Telnet protocol constants and handling utilities."""

from __future__ import annotations

from typing import Any

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
OPT_LINEMODE = 34

# Terminal type subnegotiation
TTYPE_IS = 0

# Character encoding
CP437 = "cp437"


class TelnetProtocol:
    """Handles telnet protocol negotiation and command processing."""

    def __init__(self, writer: Any, negotiated: dict[str, set[int]]) -> None:
        """Initialize protocol handler.

        Args:
            writer: Asyncio StreamWriter for sending commands
            negotiated: Dictionary tracking negotiated options by type
        """
        self._writer = writer
        self._negotiated = negotiated

    async def send_will(self, opt: int) -> None:
        """Send WILL command for option."""
        if opt not in self._negotiated["will"]:
            await self._send_cmd(WILL, opt)
            self._negotiated["will"].add(opt)

    async def send_wont(self, opt: int) -> None:
        """Send WONT command for option."""
        if opt not in self._negotiated["wont"]:
            await self._send_cmd(WONT, opt)
            self._negotiated["wont"].add(opt)

    async def send_do(self, opt: int) -> None:
        """Send DO command for option."""
        if opt not in self._negotiated["do"]:
            await self._send_cmd(DO, opt)
            self._negotiated["do"].add(opt)

    async def send_dont(self, opt: int) -> None:
        """Send DONT command for option."""
        if opt not in self._negotiated["dont"]:
            await self._send_cmd(DONT, opt)
            self._negotiated["dont"].add(opt)

    async def _send_cmd(self, cmd: int, opt: int) -> None:
        """Send a telnet command."""
        if self._writer.is_closing():
            return
        self._writer.write(bytes([IAC, cmd, opt]))
        try:
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass

    async def send_naws(self, cols: int, rows: int) -> None:
        """Send NAWS (Negotiate About Window Size) subnegotiation."""
        width_high = (cols >> 8) & 0xFF
        width_low = cols & 0xFF
        height_high = (rows >> 8) & 0xFF
        height_low = rows & 0xFF
        msg = bytes([IAC, SB, OPT_NAWS, width_high, width_low, height_high, height_low, IAC, SE])
        if self._writer.is_closing():
            return
        self._writer.write(msg)
        try:
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass

    async def send_ttype(self, term: str) -> None:
        """Send terminal type subnegotiation."""
        payload = bytes([OPT_TTYPE, TTYPE_IS]) + term.encode("ascii", errors="replace")
        await self._send_subnegotiation(payload)

    async def _send_subnegotiation(self, payload: bytes) -> None:
        """Send a telnet subnegotiation."""
        if self._writer.is_closing():
            return
        self._writer.write(bytes([IAC, SB]) + payload + bytes([IAC, SE]))
        try:
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def strip_telnet_commands(self, data: bytes) -> bytes:
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
                    result.append(IAC)
                    i += 2
                    continue
            result.append(data[i])
            i += 1
        return bytes(result)


def parse_telnet_commands(data: bytes) -> list[tuple[str, int | None]]:
    """Parse telnet commands from data stream for logging/debugging.

    Args:
        data: Raw bytes from telnet connection

    Returns:
        List of (command_name, option) tuples
    """
    commands: list[tuple[str, int | None]] = []
    i = 0
    while i < len(data):
        if data[i] == IAC and i + 1 < len(data):
            cmd = data[i + 1]
            if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                cmd_name = {DO: "DO", DONT: "DONT", WILL: "WILL", WONT: "WONT"}[cmd]
                commands.append((cmd_name, data[i + 2]))
                i += 3
            elif cmd == SB:
                commands.append(("SB", None))
                i += 2
            elif cmd == SE:
                commands.append(("SE", None))
                i += 2
            else:
                i += 1
        else:
            i += 1
    return commands
