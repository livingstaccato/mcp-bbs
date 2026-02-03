"""Mock BBS server for testing."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any


class MockBBSServer:
    """Simple mock BBS server for testing telnet connections."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        """Initialize mock BBS server.

        Args:
            host: Host to bind to
            port: Port to bind to (0 = random available port)
        """
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.clients: list[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = []
        self.responses: list[bytes] = []
        self.received: list[bytes] = []

    def add_response(self, data: str | bytes) -> None:
        """Add a response to send to clients."""
        if isinstance(data, str):
            data = data.encode("cp437")
        self.responses.append(data)

    async def start(self) -> None:
        """Start the mock BBS server."""
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        # Update port to actual assigned port
        addr = self.server.sockets[0].getsockname()
        self.port = addr[1]

    async def stop(self) -> None:
        """Stop the mock BBS server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for _, writer in self.clients:
            writer.close()
            await writer.wait_closed()
        self.clients.clear()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a client connection."""
        self.clients.append((reader, writer))

        # Send welcome screen
        if self.responses:
            welcome = self.responses[0]
            writer.write(welcome)
            await writer.drain()

        # Echo loop - read and optionally respond
        response_idx = 1
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break

                self.received.append(data)

                # Send next response if available
                if response_idx < len(self.responses):
                    writer.write(self.responses[response_idx])
                    await writer.drain()
                    response_idx += 1

        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            self.clients.remove((reader, writer))


class MockBBS:
    """Context manager for mock BBS server."""

    def __init__(
        self, responses: list[str] | None = None, replay_log: Path | str | None = None
    ) -> None:
        """Initialize mock BBS.

        Args:
            responses: List of responses to send (first is welcome screen)
            replay_log: Path to JSONL session log to replay
        """
        self.server = MockBBSServer()
        if replay_log:
            self._load_replay_log(replay_log)
        elif responses:
            for response in responses:
                self.server.add_response(response)

    def _load_replay_log(self, log_path: Path | str) -> None:
        """Load responses from JSONL session log.

        Extracts raw_bytes_b64 from read events and uses them as responses.
        """
        if isinstance(log_path, str):
            log_path = Path(log_path)

        with open(log_path) as f:
            for line in f:
                if not line.strip():
                    continue

                record = json.loads(line)
                event = record.get("event")
                data = record.get("data", {})

                # Extract raw bytes from read events
                if event == "read" and "raw_bytes_b64" in data:
                    raw_bytes = base64.b64decode(data["raw_bytes_b64"])
                    if raw_bytes:  # Skip empty reads
                        self.server.add_response(raw_bytes)

    async def __aenter__(self) -> MockBBSServer:
        """Start the server."""
        await self.server.start()
        return self.server

    async def __aexit__(self, *args: Any) -> None:
        """Stop the server."""
        await self.server.stop()
