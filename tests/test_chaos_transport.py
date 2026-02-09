from __future__ import annotations

import pytest

from bbsbot.transport.base import ConnectionTransport
from bbsbot.transport.chaos import ChaosTransport


class DummyTransport(ConnectionTransport):
    def __init__(self) -> None:
        self.connected = False
        self.rx_calls = 0

    async def connect(self, host: str, port: int, **kwargs) -> None:  # noqa: ANN001
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def send(self, data: bytes) -> None:
        if not self.connected:
            raise ConnectionError("Not connected")

    async def receive(self, max_bytes: int, timeout_ms: int) -> bytes:
        if not self.connected:
            raise ConnectionError("Not connected")
        self.rx_calls += 1
        return b"hello"

    def is_connected(self) -> bool:
        return self.connected


@pytest.mark.asyncio
async def test_chaos_disconnect_every_n_receives() -> None:
    inner = DummyTransport()
    transport = ChaosTransport(inner, seed=1, disconnect_every_n_receives=2, label="t")
    await transport.connect("x", 1)

    data1 = await transport.receive(1024, 10)
    assert data1 == b"hello"
    assert inner.is_connected()

    with pytest.raises(ConnectionError):
        await transport.receive(1024, 10)
    assert not inner.is_connected()


@pytest.mark.asyncio
async def test_chaos_timeout_every_n_receives_returns_empty() -> None:
    inner = DummyTransport()
    transport = ChaosTransport(inner, seed=1, timeout_every_n_receives=1, label="t")
    await transport.connect("x", 1)

    data = await transport.receive(1024, 1)
    assert data == b""
    assert inner.is_connected()

