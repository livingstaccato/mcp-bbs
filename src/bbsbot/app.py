from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.mcp.server import create_app as create_mcp_app
from bbsbot.settings import Settings

if TYPE_CHECKING:
    from fastmcp import FastMCP


def create_app(settings: Settings | None = None, tool_prefixes: str | None = None) -> FastMCP:
    """Create and configure the FastMCP app.

    Args:
        settings: Application settings (defaults to Settings())
        tool_prefixes: Comma-separated tool namespaces to include (e.g., 'bbs' or 'bbs,tw2002')
    """
    return create_mcp_app(settings or Settings(), tool_prefixes=tool_prefixes)


__all__ = ["create_app"]
