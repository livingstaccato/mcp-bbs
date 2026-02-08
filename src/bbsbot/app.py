from __future__ import annotations

from fastmcp import FastMCP

from bbsbot.mcp.server import create_app as create_mcp_app
from bbsbot.settings import Settings


def create_app(settings: Settings | None = None, game_filter: str | None = None) -> FastMCP:
    """Create and configure the FastMCP app.

    Args:
        settings: Application settings (defaults to Settings())
        game_filter: If provided, only register tools for this game
    """
    return create_mcp_app(settings or Settings(), game_filter=game_filter)


__all__ = ["create_app"]
