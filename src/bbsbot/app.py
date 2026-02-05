from __future__ import annotations

from fastmcp import FastMCP

from bbsbot.mcp.server import create_app as create_mcp_app
from bbsbot.settings import Settings
from bbsbot.watch import WatchManager, watch_settings


def create_app(settings: Settings | None = None) -> FastMCP:
    """Create and configure the FastMCP app."""
    app = create_mcp_app(settings or Settings())
    manager: WatchManager | None = None

    if watch_settings.enabled:
        manager = WatchManager()

        @app.on_startup
        async def _watch_startup() -> None:
            await manager.start()

        @app.on_shutdown
        async def _watch_shutdown() -> None:
            await manager.stop()

        app.state["watch_manager"] = manager

    return app


__all__ = ["create_app"]
