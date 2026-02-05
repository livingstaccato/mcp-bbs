from __future__ import annotations

from fastmcp import FastMCP

from bbsbot.mcp.server import create_app as create_mcp_app
from bbsbot.settings import Settings


def create_app(settings: Settings | None = None) -> FastMCP:
    """Create and configure the FastMCP app."""
    return create_mcp_app(settings or Settings())


__all__ = ["create_app"]
