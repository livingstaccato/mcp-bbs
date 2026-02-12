# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

log = structlog.get_logger()


class WatchBroker:
    """Broadcast raw ANSI bytes (and optional metadata) to TCP watchers."""

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._lock = asyncio.Lock()

    async def start(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._on_client, host=host, port=port)
        log.info("watch_broker_started", host=host, port=port)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        async with self._lock:
            for writer in list(self._clients):
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
            self._clients.clear()
        log.info("watch_broker_stopped")

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async with self._lock:
            self._clients.add(writer)
        addr = writer.get_extra_info("peername")
        log.info("watch_client_connected", peer=str(addr))
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
        except Exception:
            pass
        finally:
            async with self._lock:
                self._clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            log.info("watch_client_disconnected", peer=str(addr))

    async def broadcast_raw(self, data: bytes) -> None:
        if not data:
            return
        async with self._lock:
            writers = list(self._clients)
        if not writers:
            return
        for writer in writers:
            try:
                writer.write(data)
                await writer.drain()
            except Exception:
                async with self._lock:
                    self._clients.discard(writer)
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

    async def broadcast_event(self, event: str, payload: dict[str, Any]) -> None:
        message = json.dumps({"event": event, "data": payload}) + "\n"
        await self.broadcast_raw(message.encode("utf-8"))
