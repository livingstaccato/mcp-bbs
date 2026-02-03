"""Test JSONL session replay functionality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_bbs.telnet import TelnetClient

from .mock_bbs_server import MockBBS


@pytest.mark.asyncio
async def test_replay_jsonl_session(tmp_path: Path) -> None:
    """Test replaying a JSONL session log through mock BBS."""
    # Create a sample JSONL log
    log_file = tmp_path / "sample_session.jsonl"

    # Sample log entries with raw bytes
    log_entries = [
        {
            "ts": 1234567890.0,
            "event": "connect",
            "data": {"host": "127.0.0.1", "port": 2002},
        },
        {
            "ts": 1234567891.0,
            "event": "read",
            "data": {
                "screen": "Welcome to BBS\nMain Menu\n[M] Messages",
                "raw": "Welcome to BBS\r\nMain Menu\r\n[M] Messages",
                "raw_bytes_b64": "V2VsY29tZSB0byBCQlMNCk1haW4gTWVudQ0KW01dIE1lc3NhZ2Vz",
            },
        },
        {
            "ts": 1234567892.0,
            "event": "send",
            "data": {"keys": "M\r"},
        },
        {
            "ts": 1234567893.0,
            "event": "read",
            "data": {
                "screen": "Message List\n1. Hello World",
                "raw": "Message List\r\n1. Hello World",
                "raw_bytes_b64": "TWVzc2FnZSBMaXN0DQoxLiBIZWxsbyBXb3JsZA==",
            },
        },
    ]

    with open(log_file, "w") as f:
        for entry in log_entries:
            f.write(json.dumps(entry) + "\n")

    # Replay the session
    async with MockBBS(replay_log=log_file) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        # Read first response (welcome)
        snapshot1 = await client.read(timeout_ms=500, max_bytes=8192)
        assert "Welcome to BBS" in snapshot1["screen"]
        assert "Main Menu" in snapshot1["screen"]

        # Send a key
        await client.send("M\r")

        # Read second response (message list)
        snapshot2 = await client.read(timeout_ms=500, max_bytes=8192)
        assert "Message List" in snapshot2["screen"]

        await client.disconnect()


@pytest.mark.asyncio
async def test_replay_empty_log(tmp_path: Path) -> None:
    """Test replaying an empty JSONL log."""
    log_file = tmp_path / "empty.jsonl"
    log_file.write_text("")

    # Should handle gracefully
    async with MockBBS(replay_log=log_file) as server:
        client = TelnetClient()
        await client.connect("127.0.0.1", server.port, 80, 25, "ANSI", False, False)

        # Should timeout since no responses
        snapshot = await client.read(timeout_ms=100, max_bytes=8192)
        assert snapshot["screen"] == ""

        await client.disconnect()
