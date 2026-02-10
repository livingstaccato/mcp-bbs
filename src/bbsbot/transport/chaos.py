"""Fault-injection transport wrapper (deterministic).

This is used for resilience testing. It wraps a real transport and injects
timeouts/disconnects at deterministic intervals so tests are repeatable.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from typing import Any

from bbsbot.transport.base import ConnectionTransport


class ChaosTransport(ConnectionTransport):
    def __init__(
        self,
        inner: ConnectionTransport,
        *,
        seed: int = 1,
        disconnect_every_n_receives: int = 0,
        timeout_every_n_receives: int = 0,
        max_jitter_ms: int = 0,
        label: str = "chaos",
    ) -> None:
        self._inner = inner
        self._rng = random.Random(int(seed))
        self._disconnect_n = int(disconnect_every_n_receives or 0)
        self._timeout_n = int(timeout_every_n_receives or 0)
        self._max_jitter_ms = int(max_jitter_ms or 0)
        self._label = str(label or "chaos")
        self._rx_count = 0

    async def connect(self, host: str, port: int, **kwargs: Any) -> None:
        await self._inner.connect(host, port, **kwargs)

    async def disconnect(self) -> None:
        await self._inner.disconnect()

    async def send(self, data: bytes) -> None:
        await self._inner.send(data)

    async def receive(self, max_bytes: int, timeout_ms: int) -> bytes:
        self._rx_count += 1

        if self._max_jitter_ms > 0:
            await asyncio.sleep(self._rng.uniform(0.0, float(self._max_jitter_ms)) / 1000.0)

        if self._disconnect_n > 0 and (self._rx_count % self._disconnect_n) == 0:
            with contextlib.suppress(Exception):
                await self._inner.disconnect()
            raise ConnectionError(f"{self._label}: injected disconnect on receive #{self._rx_count}")

        if self._timeout_n > 0 and (self._rx_count % self._timeout_n) == 0:
            # Simulate a read timeout without touching the underlying transport.
            await asyncio.sleep(max(0.0, float(timeout_ms)) / 1000.0)
            return b""

        return await self._inner.receive(max_bytes=max_bytes, timeout_ms=timeout_ms)

    def is_connected(self) -> bool:
        return self._inner.is_connected()
