"""Tests for BBS client functionality."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.mcp_config import StdioMCPServer


@pytest.mark.asyncio
async def test_bbs_connection(bbs_host: str, bbs_port: int) -> None:
    """Test basic BBS connection and interaction."""
    server = StdioMCPServer(
        command="mcp-bbs",
        args=[],
    )
    async with Client(server.to_transport()) as client:
        await client.call_tool(
            "bbs_connect",
            {
                "host": bbs_host,
                "port": bbs_port,
                "cols": 80,
                "rows": 25,
                "term": "ANSI",
                "send_newline": True,
            },
        )
        await client.call_tool("bbs_wake", {})
        snap = await client.call_tool(
            "bbs_read_until_pattern",
            {
                "pattern": r"Please enter your name",
                "timeout_ms": 8000,
            },
        )
        assert snap.data is not None and "screen" in snap.data
        await client.call_tool("bbs_disconnect", {})
