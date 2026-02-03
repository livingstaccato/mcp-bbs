"""Integration tests for TelnetClient using mock BBS server."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcp_bbs.telnet import TelnetClient

from .mock_bbs_server import MockBBS


@pytest.mark.asyncio
async def test_telnet_client_connect_disconnect() -> None:
    """Test basic connect and disconnect."""
    async with MockBBS(["\r\nWelcome to Mock BBS\r\n"]) as server:
        client = TelnetClient()

        # Connect
        result = await client.connect(
            "127.0.0.1", server.port, 80, 25, "ANSI", False, False
        )
        assert result == "ok"

        # Check status
        status = client.status()
        assert status["connected"] is True
        assert status["cols"] == 80
        assert status["rows"] == 25
        assert status["host"] == "127.0.0.1"

        # Disconnect
        result = await client.disconnect()
        assert result == "ok"

        status = client.status()
        assert status["connected"] is False


@pytest.mark.asyncio
async def test_telnet_client_read() -> None:
    """Test reading from BBS."""
    async with MockBBS(["\r\nWelcome to Mock BBS\r\n[M] Main Menu\r\n"]) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        # Read with timeout
        snapshot = await client.read(timeout_ms=500, max_bytes=8192)

        assert "screen" in snapshot
        assert "Welcome to Mock BBS" in snapshot["screen"]
        assert "raw" in snapshot
        assert "screen_hash" in snapshot
        assert "cursor" in snapshot
        assert snapshot["cols"] == 80
        assert snapshot["rows"] == 25

        await client.disconnect()


@pytest.mark.asyncio
async def test_telnet_client_send() -> None:
    """Test sending keys to BBS."""
    async with MockBBS(
        ["\r\nMain Menu\r\n", "\r\nYou pressed M\r\n"]
    ) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        # Wait for welcome
        await asyncio.sleep(0.1)

        # Send keys
        result = await client.send("M\r")
        assert result == "ok"

        # Read response
        await asyncio.sleep(0.1)
        snapshot = await client.read(timeout_ms=500, max_bytes=8192)
        assert "You pressed M" in snapshot["screen"]

        await client.disconnect()


@pytest.mark.asyncio
async def test_telnet_client_read_until_pattern() -> None:
    """Test reading until pattern matches."""
    async with MockBBS(["\r\nLoading...\r\n", "\r\nMain Menu\r\n"]) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        # Send a key to trigger response
        await client.send("M")

        # Read until pattern
        snapshot = await client.read_until_pattern(
            pattern=r"Main Menu", timeout_ms=2000, interval_ms=100, max_bytes=8192
        )

        assert snapshot["matched"] is True
        assert "Main Menu" in snapshot["screen"]

        await client.disconnect()


@pytest.mark.asyncio
async def test_telnet_client_read_until_nonblank() -> None:
    """Test reading until screen has content."""
    async with MockBBS(["\r\n\r\n\r\nWelcome!\r\n"]) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        snapshot = await client.read_until_nonblank(
            timeout_ms=2000, interval_ms=100, max_bytes=8192
        )

        assert snapshot["screen"].strip() != ""
        assert "Welcome" in snapshot["screen"]

        await client.disconnect()


@pytest.mark.asyncio
async def test_telnet_client_expect() -> None:
    """Test expect (alias for read_until_pattern)."""
    async with MockBBS(["\r\nEnter your name: "]) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        snapshot = await client.expect(
            pattern=r"Enter your name", timeout_ms=2000, interval_ms=100
        )

        assert snapshot["matched"] is True
        assert "Enter your name" in snapshot["screen"]

        await client.disconnect()


@pytest.mark.asyncio
async def test_telnet_client_wake() -> None:
    """Test wake with key sequence."""
    async with MockBBS(
        ["\r\n\r\n", "\r\nStill sleeping\r\n", "\r\nAwake!\r\n"]
    ) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        snapshot = await client.wake(
            timeout_ms=2000, interval_ms=100, max_bytes=8192, keys_sequence=["\r", " "]
        )

        assert "screen" in snapshot

        await client.disconnect()


@pytest.mark.asyncio
async def test_telnet_client_set_size() -> None:
    """Test changing terminal size."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        # Change size
        result = await client.set_size(132, 43)
        assert result == "ok"

        status = client.status()
        assert status["cols"] == 132
        assert status["rows"] == 43

        await client.disconnect()


@pytest.mark.asyncio
async def test_telnet_client_reuse_connection() -> None:
    """Test connection reuse."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        client = TelnetClient()

        # First connect
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        # Reuse connection
        result = await client.connect(
            "127.0.0.1", server.port, 80, 25, "ANSI", False, True
        )
        assert result == "ok"

        status = client.status()
        assert status["connected"] is True

        await client.disconnect()


@pytest.mark.asyncio
async def test_telnet_client_logging(tmp_path: Path) -> None:
    """Test session logging."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        client = TelnetClient()
        log_file = tmp_path / "session.jsonl"

        # Start logging
        result = client.log_start(str(log_file))
        assert result == "ok"

        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)
        await client.read(timeout_ms=500, max_bytes=8192)

        # Add a note
        result = client.log_note({"test": "value"})
        assert result == "ok"

        # Stop logging
        result = client.log_stop()
        assert result == "ok"

        await client.disconnect()

        # Check log file exists and has content
        assert log_file.exists()
        content = log_file.read_text()
        assert "log_start" in content
        assert "connect" in content
        assert "read" in content
        assert "note" in content


@pytest.mark.asyncio
async def test_telnet_client_context() -> None:
    """Test setting context metadata."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        client = TelnetClient()

        # Set context
        result = client.set_context({"menu": "main", "action": "reading"})
        assert result == "ok"

        status = client.status()
        assert status["context"]["menu"] == "main"
        assert status["context"]["action"] == "reading"

        # Clear context
        result = client.clear_context()
        assert result == "ok"

        status = client.status()
        assert status["context"] == {}


@pytest.mark.asyncio
async def test_telnet_client_auto_learn() -> None:
    """Test auto-learning configuration."""
    client = TelnetClient()

    # Enable auto-learn
    result = client.set_auto_learn(True)
    assert result == "ok"

    # Set prompt rules
    rules = [
        {
            "prompt_id": "test",
            "regex": "test",
            "input_type": "text",
            "example_input": "example",
        }
    ]
    result = client.set_auto_prompt_rules(rules)
    assert result == "ok"

    # Set menu rules
    result = client.set_auto_menu_rules([{"menu_id": "main", "regex": "Main"}])
    assert result == "ok"

    # Enable auto-discovery
    result = client.set_auto_discover_menus(True)
    assert result == "ok"


@pytest.mark.asyncio
async def test_telnet_client_knowledge_root(tmp_path: Path) -> None:
    """Test knowledge root configuration."""
    client = TelnetClient()

    # Set knowledge root
    knowledge_root = tmp_path / "knowledge"
    result = client.set_knowledge_root(str(knowledge_root))
    assert result == "ok"

    # Get knowledge root
    retrieved = client.get_knowledge_root()
    assert retrieved == str(knowledge_root)

    # Check learn_base_dir
    base_dir = client.learn_base_dir()
    assert str(knowledge_root) in str(base_dir)
    assert "shared/bbs" in str(base_dir)


@pytest.mark.asyncio
async def test_telnet_client_keepalive() -> None:
    """Test keepalive configuration."""
    async with MockBBS(["\r\nWelcome\r\n"]) as server:
        client = TelnetClient()

        # Configure keepalive
        result = client.set_keepalive(30.0, "\r")
        assert result == "ok"

        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        status = client.status()
        assert status["keepalive"]["interval_s"] == 30.0
        assert status["keepalive"]["keys"] == "\r"

        # Disable keepalive
        result = client.set_keepalive(None, "\r")
        assert result == "ok"

        await client.disconnect()
