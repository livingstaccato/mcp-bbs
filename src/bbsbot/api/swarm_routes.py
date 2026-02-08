"""Swarm bot management API routes.

Handles spawning, killing, restarting, and status updates for bots.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.manager import SwarmManager

logger = get_logger(__name__)

router = APIRouter()

# Reference to the manager instance, set during setup
_manager: SwarmManager | None = None


class SpawnBatchRequest(BaseModel):
    """Request body for batch spawning bots."""

    config_paths: list[str]


def setup(manager: SwarmManager) -> APIRouter:
    """Configure router with manager reference.

    Args:
        manager: SwarmManager instance

    Returns:
        Configured APIRouter
    """
    global _manager  # noqa: PLW0603
    _manager = manager
    return router


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.post("/swarm/spawn")
async def spawn(config_path: str, bot_id: str = ""):
    assert _manager is not None
    try:
        if not bot_id:
            bot_id = f"bot_{len(_manager.bots):03d}"
        bot_id = await _manager.spawn_bot(config_path, bot_id)
        return {"bot_id": bot_id, "pid": _manager.bots[bot_id].pid}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post("/swarm/spawn-batch")
async def spawn_batch(request: SpawnBatchRequest):
    assert _manager is not None
    try:
        bot_ids = await _manager.spawn_swarm(request.config_paths)
        return {"bot_ids": bot_ids, "count": len(bot_ids)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get("/swarm/status")
async def status():
    assert _manager is not None
    from dataclasses import asdict

    return asdict(_manager.get_swarm_status())


@router.get("/bot/{bot_id}/status")
async def bot_status(bot_id: str):
    assert _manager is not None
    from dataclasses import asdict

    if bot_id not in _manager.bots:
        return JSONResponse(
            {"error": f"Bot {bot_id} not found"}, status_code=404
        )
    return asdict(_manager.bots[bot_id])


@router.post("/bot/{bot_id}/status")
async def update_status(bot_id: str, update: dict):
    assert _manager is not None
    if bot_id not in _manager.bots:
        return JSONResponse(
            {"error": f"Bot {bot_id} not found"}, status_code=404
        )
    bot = _manager.bots[bot_id]
    if "sector" in update:
        bot.sector = update["sector"]
    if "credits" in update:
        bot.credits = update["credits"]
    if "turns_executed" in update:
        bot.turns_executed = update["turns_executed"]
    if "state" in update:
        bot.state = update["state"]
    import time

    bot.last_update_time = time.time()
    return {"ok": True}


@router.post("/bot/{bot_id}/register")
async def register_bot(bot_id: str, data: dict):
    assert _manager is not None
    import time

    if bot_id in _manager.bots:
        _manager.bots[bot_id].last_update_time = time.time()
    return {"ok": True}


@router.post("/bot/{bot_id}/pause")
async def pause(bot_id: str):
    """Deprecated: pause is not supported by workers."""
    logger.warning("pause endpoint called but is deprecated (no-op)")
    return {"bot_id": bot_id, "state": "running", "deprecated": True}


@router.post("/bot/{bot_id}/resume")
async def resume(bot_id: str):
    """Deprecated: resume is not supported by workers."""
    logger.warning("resume endpoint called but is deprecated (no-op)")
    return {"bot_id": bot_id, "state": "running", "deprecated": True}


@router.post("/bot/{bot_id}/set-goal")
async def set_goal(bot_id: str, goal: str):
    assert _manager is not None
    if bot_id not in _manager.bots:
        return JSONResponse(
            {"error": f"Bot {bot_id} not found"}, status_code=404
        )
    return {"bot_id": bot_id, "goal": goal}


@router.delete("/bot/{bot_id}")
async def kill(bot_id: str):
    assert _manager is not None
    if bot_id not in _manager.bots:
        return JSONResponse(
            {"error": f"Bot {bot_id} not found"}, status_code=404
        )
    await _manager.kill_bot(bot_id)
    return {"killed": bot_id}


@router.post("/bot/{bot_id}/restart")
async def restart_bot(bot_id: str):
    """Restart a bot by killing it and respawning with same config.

    Works for bots in any state: running, completed, error, stopped.
    """
    assert _manager is not None
    if bot_id not in _manager.bots:
        return JSONResponse(
            {"error": f"Bot {bot_id} not found"}, status_code=404
        )

    config = _manager.bots[bot_id].config

    # Kill if still running
    if bot_id in _manager.processes:
        await _manager.kill_bot(bot_id)
        await asyncio.sleep(1)

    # Remove old status entry
    _manager.bots.pop(bot_id, None)

    # Respawn
    try:
        await _manager.spawn_bot(config, bot_id)
        return {
            "bot_id": bot_id,
            "state": "running",
            "pid": _manager.bots[bot_id].pid,
        }
    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to restart: {e}"}, status_code=500
        )
