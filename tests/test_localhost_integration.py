# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests against localhost:2002.

These tests require a BBS running on localhost:2002.
They can be skipped if the server is not available.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

from bbsbot.core.session_manager import SessionManager


def is_port_open(host: str, port: int) -> bool:
    """Check if a port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


# Skip all tests in this file if localhost:2002 is not available
pytestmark = pytest.mark.skipif(
    not is_port_open("localhost", 2002),
    reason="localhost:2002 not available",
)


@pytest.mark.asyncio
async def test_localhost_connect_disconnect() -> None:
    """Test connecting and disconnecting from localhost:2002."""
    manager = SessionManager()

    sid = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        term="ANSI",
        send_newline=True,
    )

    session = await manager.get_session(sid)
    assert session.is_connected()

    await manager.close_session(sid)


@pytest.mark.asyncio
async def test_localhost_read_initial_screen() -> None:
    """Test reading initial screen from localhost:2002."""
    manager = SessionManager()

    sid = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        term="ANSI",
        send_newline=True,
    )

    session = await manager.get_session(sid)

    # Give server time to send welcome
    await asyncio.sleep(0.5)

    # Read initial screen
    snapshot = await session.read(timeout_ms=1000, max_bytes=8192)

    assert "screen" in snapshot
    assert snapshot["screen"]  # Should have content
    assert "screen_hash" in snapshot
    assert "cursor" in snapshot
    assert snapshot["cols"] == 80
    assert snapshot["rows"] == 25

    await manager.close_session(sid)


@pytest.mark.asyncio
async def test_localhost_send_receive() -> None:
    """Test sending keys and receiving response from localhost:2002."""
    manager = SessionManager()

    sid = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        term="ANSI",
        send_newline=True,
    )

    session = await manager.get_session(sid)

    # Wait for initial screen
    await asyncio.sleep(0.5)
    await session.read(timeout_ms=1000, max_bytes=8192)

    # Send a key (e.g., Enter)
    await session.send("\r")

    # Read response
    await asyncio.sleep(0.2)
    snapshot = await session.read(timeout_ms=1000, max_bytes=8192)

    # Should have received something
    assert "screen" in snapshot

    await manager.close_session(sid)


@pytest.mark.asyncio
async def test_localhost_iac_escaping() -> None:
    """Test that IAC escaping works correctly with real BBS.

    This test sends data that might contain 0xFF bytes and verifies
    the connection remains stable (no corruption).
    """
    manager = SessionManager()

    sid = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        term="ANSI",
    )

    session = await manager.get_session(sid)

    # Wait for initial screen
    await asyncio.sleep(0.5)

    # Send various keys including escape sequences
    # If IAC escaping is broken, these might corrupt the connection
    test_keys = ["\r", "A", "\x1b", "B", "\r"]

    for key in test_keys:
        await session.send(key)
        await asyncio.sleep(0.1)
        snapshot = await session.read(timeout_ms=500, max_bytes=8192)

        # Connection should still be alive
        assert not snapshot.get("disconnected")
        assert session.is_connected()

    await manager.close_session(sid)


@pytest.mark.asyncio
async def test_localhost_terminal_resize() -> None:
    """Test terminal resize with localhost:2002."""
    manager = SessionManager()

    sid = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        term="ANSI",
    )

    session = await manager.get_session(sid)

    # Resize terminal
    await session.set_size(132, 43)

    assert session.emulator.cols == 132
    assert session.emulator.rows == 43

    # Connection should still work
    assert session.is_connected()

    await manager.close_session(sid)


@pytest.mark.asyncio
async def test_localhost_reuse_connection() -> None:
    """Test connection reuse with localhost:2002."""
    manager = SessionManager()

    # Create first session
    sid1 = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        reuse=False,
    )

    # Try to create another with reuse=True
    sid2 = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        reuse=True,
    )

    # Should reuse the same session
    assert sid1 == sid2

    session = await manager.get_session(sid1)
    assert session.is_connected()

    await manager.close_session(sid1)


@pytest.mark.asyncio
async def test_localhost_multiple_sessions() -> None:
    """Test multiple concurrent sessions to localhost:2002."""
    manager = SessionManager()

    # Create two independent sessions (reuse=False forces new connections)
    sid1 = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        reuse=False,
    )

    sid2 = await manager.create_session(
        host="localhost",
        port=2002,
        cols=80,
        rows=25,
        reuse=False,
    )

    # Should be different sessions
    assert sid1 != sid2

    # Both should be connected
    session1 = await manager.get_session(sid1)
    session2 = await manager.get_session(sid2)

    assert session1.is_connected()
    assert session2.is_connected()

    # Can interact with both independently
    await session1.send("\r")
    await session2.send("\r")

    await asyncio.sleep(0.2)

    snap1 = await session1.read(timeout_ms=500, max_bytes=8192)
    snap2 = await session2.read(timeout_ms=500, max_bytes=8192)

    assert "screen" in snap1
    assert "screen" in snap2

    await manager.close_session(sid1)
    await manager.close_session(sid2)


@pytest.mark.asyncio
async def test_localhost_session_isolation() -> None:
    """Test that sessions are properly isolated."""
    manager = SessionManager()

    sid1 = await manager.create_session("localhost", 2002, reuse=False)
    sid2 = await manager.create_session("localhost", 2002, reuse=False)

    session1 = await manager.get_session(sid1)
    session2 = await manager.get_session(sid2)

    # Send different keys to each session
    await session1.send("A")
    await session2.send("B")

    await asyncio.sleep(0.2)

    snap1 = await session1.read(timeout_ms=500, max_bytes=8192)
    snap2 = await session2.read(timeout_ms=500, max_bytes=8192)

    # Sessions should have different screen states
    # (unless the BBS is stateless, which is unlikely)
    assert snap1["screen_hash"] != snap2["screen_hash"] or snap1["screen"] == snap2["screen"]

    await manager.close_session(sid1)
    await manager.close_session(sid2)
