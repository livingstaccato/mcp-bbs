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
    if "turns_max" in update:
        bot.turns_max = update["turns_max"]
    if "state" in update:
        bot.state = update["state"]
    if "last_action" in update:
        bot.last_action = update["last_action"]
    if "last_action_time" in update:
        bot.last_action_time = update["last_action_time"]
    if "activity_context" in update:
        bot.activity_context = update["activity_context"]
    if "error_message" in update:
        bot.error_message = update["error_message"]
    if "error_type" in update:
        bot.error_type = update["error_type"]
    if "error_timestamp" in update:
        bot.error_timestamp = update["error_timestamp"]
    if "exit_reason" in update:
        bot.exit_reason = update["exit_reason"]
    if "recent_actions" in update:
        bot.recent_actions = update["recent_actions"]
    if "username" in update:
        bot.username = update["username"]
    if "ship_name" in update:
        bot.ship_name = update["ship_name"]
    if "ship_level" in update:
        bot.ship_level = update["ship_level"]
    if "port_location" in update:
        bot.port_location = update["port_location"]
    import time

    bot.last_update_time = time.time()
    await _manager._broadcast_status()
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


@router.get("/bot/{bot_id}/events")
async def get_bot_events(bot_id: str):
    """Get simplified event ledger for a bot (state changes, errors, key milestones)."""
    assert _manager is not None
    if bot_id not in _manager.bots:
        return JSONResponse(
            {"error": f"Bot {bot_id} not found", "events": []},
            status_code=404,
        )

    bot = _manager.bots[bot_id]
    import time as time_module

    events = []
    now = time_module.time()

    # Add state/activity-based events from recent actions
    if bot.recent_actions:
        for action in bot.recent_actions:
            action_time = action.get("time", 0)
            events.append({
                "timestamp": action_time,
                "type": "action",
                "action": action.get("action", "UNKNOWN"),
                "sector": action.get("sector"),
                "result": action.get("result"),
                "details": action.get("details"),
            })

    # Add error event if applicable
    if bot.error_timestamp:
        events.append({
            "timestamp": bot.error_timestamp,
            "type": "error",
            "error_type": bot.error_type,
            "error_message": bot.error_message,
        })

    # Add state change event
    if bot.last_update_time:
        events.append({
            "timestamp": bot.last_update_time,
            "type": "status_update",
            "state": bot.state,
            "activity": bot.activity_context,
            "sector": bot.sector,
            "credits": bot.credits,
            "turns_executed": bot.turns_executed,
        })

    # Sort by timestamp descending (most recent first)
    events.sort(key=lambda e: e["timestamp"], reverse=True)

    return {
        "bot_id": bot_id,
        "state": bot.state,
        "events": events[:50],  # Return last 50 events
    }


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
