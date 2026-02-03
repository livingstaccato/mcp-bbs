"""Tests for SessionManager and Session classes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcp_bbs.core.session_manager import SessionManager

from .mock_bbs_server import MockBBS


@pytest.mark.asyncio
async def test_session_manager_create_session() -> None:
    """Test creating a new session."""
    async with MockBBS(["\r\nWelcome to Mock BBS\r\n"]) as server:
        manager = SessionManager()

        # Create session
        session_id = await manager.create_session(
            "127.0.0.1", server.port, cols=80, rows=25, term="ANSI"
        )
        assert session_id is not None

        # Get session
        session = await manager.get_session(session_id)
        assert session.is_connected()
        assert session.host == "127.0.0.1"
        assert session.port == server.port
        assert session.emulator.cols == 80
        assert session.emulator.rows == 25

        # Close session
        await manager.close_session(session_id)


@pytest.mark.asyncio
async def test_session_manager_reuse_session() -> None:
    """Test session reuse."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        manager = SessionManager()

        # Create first session
        sid1 = await manager.create_session(
            "127.0.0.1", server.port, cols=80, rows=25, reuse=False
        )

        # Try to create another session with reuse=True
        sid2 = await manager.create_session(
            "127.0.0.1", server.port, cols=80, rows=25, reuse=True
        )

        # Should reuse the same session
        assert sid1 == sid2

        await manager.close_session(sid1)


@pytest.mark.asyncio
async def test_session_manager_multiple_sessions() -> None:
    """Test managing multiple sessions."""
    async with MockBBS(["\r\nServer 1\r\n"]) as server1:
        async with MockBBS(["\r\nServer 2\r\n"]) as server2:
            manager = SessionManager()

            # Create two sessions
            sid1 = await manager.create_session("127.0.0.1", server1.port)
            sid2 = await manager.create_session("127.0.0.1", server2.port)

            assert sid1 != sid2

            # Verify both sessions exist
            session1 = await manager.get_session(sid1)
            session2 = await manager.get_session(sid2)

            assert session1.port == server1.port
            assert session2.port == server2.port

            # Close both
            await manager.close_session(sid1)
            await manager.close_session(sid2)


@pytest.mark.asyncio
async def test_session_manager_max_sessions() -> None:
    """Test max session limit."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        manager = SessionManager(max_sessions=2)

        # Create two sessions
        sid1 = await manager.create_session("127.0.0.1", server.port, reuse=False)
        sid2 = await manager.create_session("127.0.0.1", server.port, reuse=False)

        # Third should fail
        with pytest.raises(RuntimeError, match="Max sessions"):
            await manager.create_session("127.0.0.1", server.port, reuse=False)

        await manager.close_session(sid1)
        await manager.close_session(sid2)


@pytest.mark.asyncio
async def test_session_send_read() -> None:
    """Test sending and reading from session."""
    async with MockBBS(["\r\nWelcome\r\n", "\r\nYou pressed M\r\n"]) as server:
        manager = SessionManager()
        sid = await manager.create_session("127.0.0.1", server.port)
        session = await manager.get_session(sid)

        # Read initial welcome
        snapshot = await session.read(timeout_ms=500, max_bytes=8192)
        assert "screen" in snapshot
        assert "Welcome" in snapshot["screen"]

        # Send keys
        await session.send("M\r")

        # Read response
        await asyncio.sleep(0.1)
        snapshot = await session.read(timeout_ms=500, max_bytes=8192)
        assert "You pressed M" in snapshot["screen"]

        await manager.close_session(sid)


@pytest.mark.asyncio
async def test_session_set_size() -> None:
    """Test changing terminal size."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        manager = SessionManager()
        sid = await manager.create_session("127.0.0.1", server.port, cols=80, rows=25)
        session = await manager.get_session(sid)

        # Change size
        await session.set_size(132, 43)

        assert session.emulator.cols == 132
        assert session.emulator.rows == 43

        await manager.close_session(sid)


@pytest.mark.asyncio
async def test_session_logging(tmp_path: Path) -> None:
    """Test session logging."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        manager = SessionManager()
        sid = await manager.create_session("127.0.0.1", server.port)
        session = await manager.get_session(sid)

        log_file = tmp_path / "session.jsonl"

        # Enable logging
        await manager.enable_logging(sid, log_file)

        # Read some data
        await session.read(timeout_ms=500, max_bytes=8192)

        # Disable logging
        await manager.disable_logging(sid)

        await manager.close_session(sid)

        # Check log file
        assert log_file.exists()
        content = log_file.read_text()
        assert "log_start" in content
        assert "read" in content


@pytest.mark.asyncio
async def test_session_learning(tmp_path: Path) -> None:
    """Test session learning."""
    async with MockBBS(["\r\nMain Menu\r\n"]) as server:
        manager = SessionManager()
        sid = await manager.create_session("127.0.0.1", server.port)
        session = await manager.get_session(sid)

        knowledge_root = tmp_path / "knowledge"
        knowledge_root.mkdir()

        # Enable learning
        await manager.enable_learning(sid, knowledge_root)

        assert session.learning is not None
        assert not session.learning.enabled

        # Enable learning engine
        session.learning.set_enabled(True)
        assert session.learning.enabled

        # Disable learning
        await manager.disable_learning(sid)
        assert session.learning is None

        await manager.close_session(sid)


@pytest.mark.asyncio
async def test_session_disconnected_read() -> None:
    """Test reading from disconnected session."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        manager = SessionManager()
        sid = await manager.create_session("127.0.0.1", server.port)
        session = await manager.get_session(sid)

        # Disconnect
        await session.disconnect()

        # Try to read - should return disconnected snapshot
        snapshot = await session.read(timeout_ms=100, max_bytes=8192)
        assert snapshot.get("disconnected") is True

        await manager.close_session(sid)


@pytest.mark.asyncio
async def test_session_status() -> None:
    """Test session status."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        manager = SessionManager()
        sid = await manager.create_session("127.0.0.1", server.port, cols=80, rows=25)
        session = await manager.get_session(sid)

        status = session.get_status()
        assert status["session_id"] == sid
        assert status["connected"] is True
        assert status["host"] == "127.0.0.1"
        assert status["port"] == server.port
        assert status["cols"] == 80
        assert status["rows"] == 25

        await manager.close_session(sid)
