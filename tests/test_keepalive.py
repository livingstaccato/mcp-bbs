"""Tests for keepalive controller."""

from __future__ import annotations

import pytest

from bbsbot.keepalive import KeepaliveController


@pytest.mark.asyncio
async def test_keepalive_configure_enabled() -> None:
    """Test configuring keepalive with interval."""
    send_called = False

    async def mock_send(keys: str) -> str:
        nonlocal send_called
        send_called = True
        return "ok"

    def is_connected() -> bool:
        return True

    controller = KeepaliveController(mock_send, is_connected)
    result = await controller.configure(1.0, "\r")

    assert result == "ok"
    status = controller.status()
    assert status["interval_s"] == 1.0
    assert status["keys"] == "\r"


@pytest.mark.asyncio
async def test_keepalive_configure_disabled() -> None:
    """Test disabling keepalive."""

    async def mock_send(keys: str) -> str:
        return "ok"

    def is_connected() -> bool:
        return False

    controller = KeepaliveController(mock_send, is_connected)
    result = await controller.configure(0, "\r")

    assert result == "ok"
    status = controller.status()
    assert status["interval_s"] is None


@pytest.mark.asyncio
async def test_keepalive_on_connect() -> None:
    """Test keepalive starts on connect."""

    async def mock_send(keys: str) -> str:
        return "ok"

    def is_connected() -> bool:
        return True

    controller = KeepaliveController(mock_send, is_connected)
    await controller.configure(30.0, "\r")
    controller.on_connect()

    status = controller.status()
    assert status["running"] is True


@pytest.mark.asyncio
async def test_keepalive_on_disconnect() -> None:
    """Test keepalive stops on disconnect."""

    async def mock_send(keys: str) -> str:
        return "ok"

    def is_connected() -> bool:
        return False

    controller = KeepaliveController(mock_send, is_connected)
    await controller.on_disconnect()

    status = controller.status()
    assert status["running"] is False
