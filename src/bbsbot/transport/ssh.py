# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SSH transport implementation stub for future development."""

from __future__ import annotations

from typing import Any

from bbsbot.transport.base import ConnectionTransport


class SSHTransport(ConnectionTransport):
    """SSH protocol transport implementation (stub for future development)."""

    async def connect(self, host: str, port: int, **kwargs: Any) -> None:
        """Establish SSH connection to remote host."""
        raise NotImplementedError("SSH transport not yet implemented")

    async def disconnect(self) -> None:
        """Close connection and cleanup resources."""
        raise NotImplementedError("SSH transport not yet implemented")

    async def send(self, data: bytes) -> None:
        """Send raw bytes."""
        raise NotImplementedError("SSH transport not yet implemented")

    async def receive(self, max_bytes: int, timeout_ms: int) -> bytes:
        """Receive raw bytes from connection."""
        raise NotImplementedError("SSH transport not yet implemented")

    def is_connected(self) -> bool:
        """Check if connection is active."""
        return False
