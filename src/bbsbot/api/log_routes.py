# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Log viewing API routes.

Provides REST endpoints and WebSocket streaming for bot log files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket
from fastapi.responses import JSONResponse

from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.log_service import LogService

logger = get_logger(__name__)

router = APIRouter()

_log_service: LogService | None = None


def setup(log_service: LogService) -> APIRouter:
    """Configure router with log service.

    Args:
        log_service: LogService instance

    Returns:
        Configured APIRouter
    """
    global _log_service  # noqa: PLW0603
    _log_service = log_service
    return router


@router.get("/bot/{bot_id}/logs")
async def get_logs(bot_id: str, offset: int = 0, limit: int = 100):
    """Get paginated log lines for a bot."""
    assert _log_service is not None
    if not _log_service.exists(bot_id):
        return JSONResponse(
            {"error": f"No logs for bot {bot_id}", "lines": []},
            status_code=404,
        )
    return _log_service.read_logs(bot_id, offset, limit)


@router.get("/bot/{bot_id}/logs/tail")
async def tail_logs(bot_id: str, lines: int = 50):
    """Get the last N lines from a bot's log."""
    assert _log_service is not None
    if not _log_service.exists(bot_id):
        return JSONResponse(
            {"error": f"No logs for bot {bot_id}", "lines": []},
            status_code=404,
        )
    return _log_service.tail_logs(bot_id, lines)


@router.websocket("/ws/bot/{bot_id}/logs")
async def stream_logs(websocket: WebSocket, bot_id: str):
    """WebSocket endpoint for real-time log streaming."""
    assert _log_service is not None
    await websocket.accept()
    await _log_service.stream_logs(bot_id, websocket)
