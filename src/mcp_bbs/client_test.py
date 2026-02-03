from __future__ import annotations

import asyncio

from fastmcp import Client
from fastmcp.mcp_config import StdioMCPServer


async def main() -> None:
    server = StdioMCPServer(
        command="mcp-bbs",
        args=[],
    )
    async with Client(server.to_transport()) as client:
        await client.call_tool(
            "bbs_connect",
            {
                "host": "127.0.0.1",
                "port": 2002,
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
        print(snap)
        await client.call_tool("bbs_disconnect", {})


if __name__ == "__main__":
    asyncio.run(main())
