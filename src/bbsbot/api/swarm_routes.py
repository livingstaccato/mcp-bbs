# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Swarm bot management API routes.

Handles spawning, killing, restarting, and status updates for bots.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from bbsbot.games.tw2002.account_pool_store import AccountPoolStore
from bbsbot.games.tw2002.bot_identity_store import BotIdentityStore
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.manager import SwarmManager

logger = get_logger(__name__)

router = APIRouter()
_identity_store = BotIdentityStore()
_account_pool_store = AccountPoolStore()

# Reference to the manager instance, set during setup
_manager: SwarmManager | None = None


class SpawnBatchRequest(BaseModel):
    """Request body for batch spawning bots."""

    config_paths: list[str]
    # Default to serialized spawns. TW2002 sessions are capacity constrained;
    # spawning many bots concurrently causes "Failed to start game session" and disconnects.
    group_size: int = 1
    group_delay: float = 12.0


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
    total = len(request.config_paths)
    groups = (total + request.group_size - 1) // request.group_size

    # Run spawning in background so the API returns immediately.
    # Important: cancel any prior in-flight spawn; otherwise repeated spawn clicks
    # or a spawn+clear loop leaves a background task that keeps repopulating bots.
    await _manager.start_spawn_swarm(
        request.config_paths,
        group_size=request.group_size,
        group_delay=request.group_delay,
        cancel_existing=True,
    )

    return {
        "status": "spawning",
        "total_bots": total,
        "group_size": request.group_size,
        "group_delay": request.group_delay,
        "total_groups": groups,
        "estimated_time_seconds": (groups - 1) * request.group_delay,
    }


@router.get("/swarm/status")
async def status():
    assert _manager is not None
    return _manager.get_swarm_status().model_dump()


@router.get("/swarm/timeseries/info")
async def timeseries_info():
    """Get built-in swarm timeseries metadata."""
    assert _manager is not None
    return _manager.get_timeseries_info()


@router.get("/swarm/timeseries/recent")
async def timeseries_recent(limit: int = 200):
    """Get recent built-in swarm timeseries rows."""
    assert _manager is not None
    return {
        "rows": _manager.get_timeseries_recent(limit=limit),
        "info": _manager.get_timeseries_info(),
    }


@router.get("/swarm/timeseries/summary")
async def timeseries_summary(window_minutes: int = 120):
    """Get trailing-window summary from built-in swarm timeseries."""
    assert _manager is not None
    return _manager.get_timeseries_summary(window_minutes=window_minutes)


@router.get("/swarm/account-pool")
async def account_pool_summary():
    """Get pooled account lease/cooldown state + identity lifecycle summary."""
    pool = _account_pool_store.summary()
    active_bot_ids: set[str] = set()
    active_bot_statuses: dict[str, object] = {}
    if _manager is not None:
        active_states = {"running", "recovering", "blocked", "disconnected", "queued"}
        for bid, status in _manager.bots.items():
            if status.state in active_states:
                active_bot_ids.add(bid)
                active_bot_statuses[bid] = status
    now_ts = time.time()
    redacted_accounts = []
    for account in pool.get("accounts", []):
        lease = account.get("lease") or None
        lease_bot_id = str((lease or {}).get("bot_id") or "")
        lease_status = active_bot_statuses.get(lease_bot_id)
        lease_expires_at = float((lease or {}).get("lease_expires_at") or 0)
        lease_seconds_remaining = None
        if lease_expires_at > 0:
            lease_seconds_remaining = max(0, int(round(lease_expires_at - now_ts)))

        redacted_accounts.append(
            {
                "account_id": account.get("account_id"),
                "username": account.get("username"),
                "host": account.get("host"),
                "port": account.get("port"),
                "game_letter": account.get("game_letter"),
                "source": account.get("source"),
                "created_at": account.get("created_at"),
                "last_used_at": account.get("last_used_at"),
                "last_released_at": account.get("last_released_at"),
                "use_count": account.get("use_count"),
                "cooldown_until": account.get("cooldown_until"),
                "disabled": bool(account.get("disabled")),
                "lease": {
                    "bot_id": lease.get("bot_id"),
                    "leased_at": lease.get("leased_at"),
                    "lease_expires_at": lease.get("lease_expires_at"),
                    "is_hijacked": bool(getattr(lease_status, "is_hijacked", False)),
                    "hijacked_by": getattr(lease_status, "hijacked_by", None),
                    "hijacked_at": getattr(lease_status, "hijacked_at", None),
                }
                if lease
                else None,
                "lease_seconds_remaining": lease_seconds_remaining,
            }
        )

    leased_total = int(pool.get("leased") or 0)
    leased_active = 0
    if active_bot_ids:
        for account in redacted_accounts:
            lease = account.get("lease") or {}
            bot_id = str(lease.get("bot_id") or "")
            if bot_id and bot_id in active_bot_ids:
                leased_active += 1
    leased_stale = max(0, leased_total - leased_active)

    identity_records = _identity_store.list_records()
    by_source: dict[str, int] = {}
    active_sessions = 0
    for rec in identity_records:
        src = (rec.identity_source or "unknown").strip() or "unknown"
        by_source[src] = by_source.get(src, 0) + 1
        if rec.active_session_id:
            active_sessions += 1

    return {
        "pool": {
            "accounts_total": int(pool.get("accounts_total") or 0),
            "leased": leased_total,
            "leased_active": leased_active,
            "leased_stale": leased_stale,
            "cooldown": int(pool.get("cooldown") or 0),
            "available": int(pool.get("available") or 0),
            "accounts": redacted_accounts,
        },
        "identities": {
            "total": len(identity_records),
            "active": active_sessions,
            "by_source": by_source,
        },
    }


@router.post("/swarm/kill-all")
async def kill_all():
    """Kill all running bots in the swarm."""
    assert _manager is not None
    await _manager.cancel_spawn()
    killed = []
    for bot_id in list(_manager.processes.keys()):
        try:
            await _manager.kill_bot(bot_id)
            killed.append(bot_id)
        except Exception as e:
            logger.error(f"Failed to kill {bot_id}: {e}")
    return {"killed": killed, "count": len(killed)}


@router.post("/swarm/clear")
async def clear_swarm():
    """Clear all bot entries (running bots are killed first)."""
    assert _manager is not None
    await _manager.cancel_spawn()
    # Kill running bots first
    for bot_id in list(_manager.processes.keys()):
        with contextlib.suppress(Exception):
            await _manager.kill_bot(bot_id)
    count = len(_manager.bots)
    _manager.bots.clear()
    _manager.processes.clear()
    await _manager._broadcast_status()
    return {"cleared": count}


@router.get("/bot/{bot_id}/status")
async def bot_status(bot_id: str):
    assert _manager is not None
    if bot_id not in _manager.bots:
        return JSONResponse({"error": f"Bot {bot_id} not found"}, status_code=404)
    return _manager.bots[bot_id].model_dump()


@router.get("/bot/{bot_id}/session-data")
async def bot_session_data(bot_id: str):
    """Return persisted identity + session lifecycle data for one bot."""
    record = _identity_store.load(bot_id)
    if record is None:
        return JSONResponse({"error": f"No persisted session data for {bot_id}"}, status_code=404)
    return record.model_dump(mode="json")


@router.post("/bot/{bot_id}/status")
async def update_status(bot_id: str, update: dict):
    assert _manager is not None
    if bot_id not in _manager.bots:
        return JSONResponse({"error": f"Bot {bot_id} not found"}, status_code=404)
    bot = _manager.bots[bot_id]
    # Ignore out-of-order reports to prevent stale Activity/Status regressions.
    try:
        incoming_reported_at = float(update.get("reported_at") or 0.0)
    except Exception:
        incoming_reported_at = 0.0
    if incoming_reported_at > 0 and bot.status_reported_at > 0 and incoming_reported_at < bot.status_reported_at:
        return {"ok": True, "ignored": "stale_report"}
    if incoming_reported_at > 0:
        bot.status_reported_at = incoming_reported_at
    if "sector" in update:
        bot.sector = update["sector"]
    # Accept any non-negative value (including 0).
    # Only -1 means uninitialized, which we skip.
    if "credits" in update and update["credits"] >= 0:
        bot.credits = update["credits"]
    if "turns_executed" in update:
        # Keep counters monotonic within a bot process lifetime.
        # Reconnect churn can emit stale/lower snapshots and should not drag totals backward.
        new_turns = int(update["turns_executed"] or 0)
        if new_turns != bot.turns_executed:
            from bbsbot.logging import get_logger

            logger = get_logger(__name__)
            logger.debug(f"Bot {bot_id} turns: {bot.turns_executed} → {new_turns}")
        bot.turns_executed = max(int(bot.turns_executed or 0), new_turns)
    if "turns_max" in update:
        bot.turns_max = update["turns_max"]
    if "state" in update:
        bot.state = update["state"]
    if "started_at" in update:
        bot.started_at = float(update["started_at"]) if update["started_at"] is not None else None
    if "stopped_at" in update:
        bot.stopped_at = float(update["stopped_at"]) if update["stopped_at"] is not None else None
    if "last_action" in update:
        bot.last_action = update["last_action"]
    if "last_action_time" in update:
        bot.last_action_time = update["last_action_time"]
    if "activity_context" in update:
        activity = str(update["activity_context"] or "").strip()
        bot.activity_context = activity.upper() if activity else None
    if "status_detail" in update:
        detail = str(update["status_detail"] or "").strip()
        # Keep status values human-facing; avoid leaking raw prompt ids.
        if detail.startswith("prompt."):
            detail = detail.split(".", 1)[1].replace("_", " ").upper()
        bot.status_detail = detail or None
    if "prompt_id" in update:
        bot.prompt_id = update["prompt_id"]
    if "cargo_fuel_ore" in update:
        bot.cargo_fuel_ore = update["cargo_fuel_ore"]
    if "cargo_organics" in update:
        bot.cargo_organics = update["cargo_organics"]
    if "cargo_equipment" in update:
        bot.cargo_equipment = update["cargo_equipment"]
    if "cargo_estimated_value" in update:
        bot.cargo_estimated_value = int(update["cargo_estimated_value"])
    if "bank_balance" in update:
        bot.bank_balance = int(update["bank_balance"])
    if "net_worth_estimate" in update:
        bot.net_worth_estimate = int(update["net_worth_estimate"])
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
    if "strategy" in update:
        bot.strategy = update["strategy"]
    if "strategy_id" in update:
        bot.strategy_id = update["strategy_id"]
    if "strategy_mode" in update:
        bot.strategy_mode = update["strategy_mode"]
    if "swarm_role" in update:
        role = str(update["swarm_role"] or "").strip().lower()
        bot.swarm_role = role or None
    if "strategy_intent" in update:
        bot.strategy_intent = update["strategy_intent"]
    if "ship_name" in update:
        bot.ship_name = update["ship_name"]
    if "ship_level" in update:
        bot.ship_level = update["ship_level"]
    if "port_location" in update:
        bot.port_location = update["port_location"]
    if "haggle_accept" in update:
        bot.haggle_accept = int(update["haggle_accept"])
    if "haggle_counter" in update:
        bot.haggle_counter = int(update["haggle_counter"])
    if "haggle_too_high" in update:
        bot.haggle_too_high = int(update["haggle_too_high"])
    if "haggle_too_low" in update:
        bot.haggle_too_low = int(update["haggle_too_low"])
    if "trades_executed" in update:
        bot.trades_executed = max(int(bot.trades_executed or 0), int(update["trades_executed"] or 0))
    if "trade_attempts" in update:
        bot.trade_attempts = max(int(bot.trade_attempts or 0), int(update["trade_attempts"] or 0))
    if "trade_successes" in update:
        bot.trade_successes = max(int(bot.trade_successes or 0), int(update["trade_successes"] or 0))
    if "trade_failures" in update:
        bot.trade_failures = max(int(bot.trade_failures or 0), int(update["trade_failures"] or 0))
    if "trade_failure_reasons" in update:
        merged = dict(bot.trade_failure_reasons or {})
        for key, value in dict(update.get("trade_failure_reasons") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged[token] = max(int(merged.get(token, 0) or 0), int(value or 0))
        bot.trade_failure_reasons = merged
    if "trade_outcomes_by_port_resource" in update:
        merged_port = dict(bot.trade_outcomes_by_port_resource or {})
        for key, metrics in dict(update.get("trade_outcomes_by_port_resource") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            prev = dict(merged_port.get(token) or {})
            for metric, value in dict(metrics or {}).items():
                mkey = str(metric or "").strip().lower()
                if not mkey:
                    continue
                prev[mkey] = max(int(prev.get(mkey, 0) or 0), int(value or 0))
            merged_port[token] = prev
        bot.trade_outcomes_by_port_resource = merged_port
    if "trade_outcomes_by_pair" in update:
        merged_pair = dict(bot.trade_outcomes_by_pair or {})
        for key, metrics in dict(update.get("trade_outcomes_by_pair") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            prev = dict(merged_pair.get(token) or {})
            for metric, value in dict(metrics or {}).items():
                mkey = str(metric or "").strip().lower()
                if not mkey:
                    continue
                prev[mkey] = max(int(prev.get(mkey, 0) or 0), int(value or 0))
            merged_pair[token] = prev
        bot.trade_outcomes_by_pair = merged_pair
    if "credits_delta" in update:
        bot.credits_delta = int(update["credits_delta"])
    if "credits_per_turn" in update:
        bot.credits_per_turn = float(update["credits_per_turn"])
    if "turns_since_last_trade" in update:
        bot.turns_since_last_trade = max(0, int(update["turns_since_last_trade"] or 0))
    if "move_streak" in update:
        bot.move_streak = max(0, int(update["move_streak"] or 0))
    if "zero_delta_action_streak" in update:
        bot.zero_delta_action_streak = max(0, int(update["zero_delta_action_streak"] or 0))
    if "prompt_telemetry" in update:
        merged_prompt = dict(bot.prompt_telemetry or {})
        for key, value in dict(update.get("prompt_telemetry") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_prompt[token] = max(int(merged_prompt.get(token, 0) or 0), int(value or 0))
        bot.prompt_telemetry = merged_prompt
    if "warp_telemetry" in update:
        merged_warp = dict(bot.warp_telemetry or {})
        for key, value in dict(update.get("warp_telemetry") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_warp[token] = max(int(merged_warp.get(token, 0) or 0), int(value or 0))
        bot.warp_telemetry = merged_warp
    if "warp_failure_reasons" in update:
        merged_warp_reasons = dict(bot.warp_failure_reasons or {})
        for key, value in dict(update.get("warp_failure_reasons") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_warp_reasons[token] = max(int(merged_warp_reasons.get(token, 0) or 0), int(value or 0))
        bot.warp_failure_reasons = merged_warp_reasons
    if "decision_counts_considered" in update:
        merged_considered = dict(bot.decision_counts_considered or {})
        for key, value in dict(update.get("decision_counts_considered") or {}).items():
            token = str(key or "").strip().upper()
            if not token:
                continue
            merged_considered[token] = max(int(merged_considered.get(token, 0) or 0), int(value or 0))
        bot.decision_counts_considered = merged_considered
    if "decision_counts_executed" in update:
        merged_executed = dict(bot.decision_counts_executed or {})
        for key, value in dict(update.get("decision_counts_executed") or {}).items():
            token = str(key or "").strip().upper()
            if not token:
                continue
            merged_executed[token] = max(int(merged_executed.get(token, 0) or 0), int(value or 0))
        bot.decision_counts_executed = merged_executed
    if "decision_override_total" in update:
        bot.decision_override_total = max(int(bot.decision_override_total or 0), int(update["decision_override_total"] or 0))
    if "decision_override_reasons" in update:
        merged_override_reasons = dict(bot.decision_override_reasons or {})
        for key, value in dict(update.get("decision_override_reasons") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_override_reasons[token] = max(int(merged_override_reasons.get(token, 0) or 0), int(value or 0))
        bot.decision_override_reasons = merged_override_reasons
    if "valuation_source_units_total" in update:
        merged_units_total = dict(bot.valuation_source_units_total or {})
        for key, value in dict(update.get("valuation_source_units_total") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_units_total[token] = max(int(merged_units_total.get(token, 0) or 0), int(value or 0))
        bot.valuation_source_units_total = merged_units_total
    if "valuation_source_value_total" in update:
        merged_value_total = dict(bot.valuation_source_value_total or {})
        for key, value in dict(update.get("valuation_source_value_total") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_value_total[token] = max(int(merged_value_total.get(token, 0) or 0), int(value or 0))
        bot.valuation_source_value_total = merged_value_total
    if "valuation_source_units_last" in update:
        bot.valuation_source_units_last = dict(update.get("valuation_source_units_last") or {})
    if "valuation_source_value_last" in update:
        bot.valuation_source_value_last = dict(update.get("valuation_source_value_last") or {})
    if "valuation_confidence_last" in update:
        bot.valuation_confidence_last = float(update["valuation_confidence_last"] or 0.0)
    if "route_churn_total" in update:
        bot.route_churn_total = max(int(bot.route_churn_total or 0), int(update["route_churn_total"] or 0))
    if "route_churn_reasons" in update:
        merged_churn_reasons = dict(bot.route_churn_reasons or {})
        for key, value in dict(update.get("route_churn_reasons") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_churn_reasons[token] = max(int(merged_churn_reasons.get(token, 0) or 0), int(value or 0))
        bot.route_churn_reasons = merged_churn_reasons
    if "llm_wakeups" in update:
        bot.llm_wakeups = int(update["llm_wakeups"])
    if "autopilot_turns" in update:
        bot.autopilot_turns = int(update["autopilot_turns"])
    if "goal_contract_failures" in update:
        bot.goal_contract_failures = int(update["goal_contract_failures"])
    if "action_counters" in update:
        merged_actions = dict(bot.action_counters or {})
        for key, value in dict(update.get("action_counters") or {}).items():
            token = str(key or "").strip().upper()
            if not token:
                continue
            merged_actions[token] = max(int(merged_actions.get(token, 0) or 0), int(value or 0))
        bot.action_counters = merged_actions
    if "recovery_actions" in update:
        bot.recovery_actions = max(int(bot.recovery_actions or 0), int(update["recovery_actions"] or 0))
    if "combat_telemetry" in update:
        merged_combat = dict(bot.combat_telemetry or {})
        for key, value in dict(update.get("combat_telemetry") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_combat[token] = max(int(merged_combat.get(token, 0) or 0), int(value or 0))
        bot.combat_telemetry = merged_combat
    if "attrition_telemetry" in update:
        merged_attrition = dict(bot.attrition_telemetry or {})
        for key, value in dict(update.get("attrition_telemetry") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_attrition[token] = max(int(merged_attrition.get(token, 0) or 0), int(value or 0))
        bot.attrition_telemetry = merged_attrition
    if "opportunity_telemetry" in update:
        merged_opp = dict(bot.opportunity_telemetry or {})
        for key, value in dict(update.get("opportunity_telemetry") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_opp[token] = max(int(merged_opp.get(token, 0) or 0), int(value or 0))
        bot.opportunity_telemetry = merged_opp
    if "action_latency_telemetry" in update:
        merged_latency = dict(bot.action_latency_telemetry or {})
        for key, value in dict(update.get("action_latency_telemetry") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_latency[token] = max(int(merged_latency.get(token, 0) or 0), int(value or 0))
        bot.action_latency_telemetry = merged_latency
    if "delta_attribution_telemetry" in update:
        merged_delta_attr = dict(bot.delta_attribution_telemetry or {})
        for key, value in dict(update.get("delta_attribution_telemetry") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            merged_delta_attr[token] = max(int(merged_delta_attr.get(token, 0) or 0), int(value or 0))
        bot.delta_attribution_telemetry = merged_delta_attr
    if "anti_collapse_runtime" in update:
        merged_anti = dict(bot.anti_collapse_runtime or {})
        for key, value in dict(update.get("anti_collapse_runtime") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            if isinstance(value, bool):
                merged_anti[token] = bool(value)
                continue
            with contextlib.suppress(Exception):
                merged_anti[token] = max(int(merged_anti.get(token, 0) or 0), int(value or 0))
        bot.anti_collapse_runtime = merged_anti
    if "trade_quality_runtime" in update:
        merged_tq = dict(bot.trade_quality_runtime or {})
        for key, value in dict(update.get("trade_quality_runtime") or {}).items():
            token = str(key or "").strip().lower()
            if not token:
                continue
            if isinstance(value, bool):
                merged_tq[token] = bool(value)
                continue
            if isinstance(value, float):
                with contextlib.suppress(Exception):
                    merged_tq[token] = float(value)
                continue
            with contextlib.suppress(Exception):
                merged_tq[token] = max(float(merged_tq.get(token, 0) or 0), float(value or 0))
        bot.trade_quality_runtime = merged_tq
    if "llm_wakeups_per_100_turns" in update:
        bot.llm_wakeups_per_100_turns = float(update["llm_wakeups_per_100_turns"])
    if "hostile_fighters" in update:
        bot.hostile_fighters = int(update["hostile_fighters"])
    if "under_attack" in update:
        bot.under_attack = bool(update["under_attack"])
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
        return JSONResponse({"error": f"Bot {bot_id} not found"}, status_code=404)
    return {"bot_id": bot_id, "goal": goal}


@router.delete("/bot/{bot_id}")
async def kill(bot_id: str):
    assert _manager is not None
    if bot_id not in _manager.bots:
        return JSONResponse({"error": f"Bot {bot_id} not found"}, status_code=404)
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
    time_module.time()

    # Add state/activity-based events from recent actions
    if bot.recent_actions:
        for action in bot.recent_actions:
            action_time = action.get("time", 0)
            events.append(
                {
                    "timestamp": action_time,
                    "type": "action",
                    "action": action.get("action", "UNKNOWN"),
                    "sector": action.get("sector"),
                    "result": action.get("result"),
                    "details": action.get("details"),
                    "why": action.get("why"),
                    "wake_reason": action.get("wake_reason"),
                    "review_after_turns": action.get("review_after_turns"),
                    "decision_source": action.get("decision_source"),
                    "credits_before": action.get("credits_before"),
                    "credits_after": action.get("credits_after"),
                    "turns_before": action.get("turns_before"),
                    "turns_after": action.get("turns_after"),
                    "result_delta": action.get("result_delta"),
                    "strategy": bot.strategy,
                    "strategy_id": action.get("strategy_id") or bot.strategy_id,
                    "strategy_mode": action.get("strategy_mode") or bot.strategy_mode,
                    "strategy_intent": action.get("strategy_intent") or bot.strategy_intent,
                    "credits": bot.credits,
                    "turns_executed": bot.turns_executed,
                    "started_at": bot.started_at,
                    "stopped_at": bot.stopped_at,
                }
            )

    # Add error event if applicable
    if bot.error_timestamp:
        events.append(
            {
                "timestamp": bot.error_timestamp,
                "type": "error",
                "error_type": bot.error_type,
                "error_message": bot.error_message,
                "strategy": bot.strategy,
                "strategy_id": bot.strategy_id,
                "strategy_mode": bot.strategy_mode,
                "strategy_intent": bot.strategy_intent,
                "llm_wakeups": bot.llm_wakeups,
                "autopilot_turns": bot.autopilot_turns,
                "goal_contract_failures": bot.goal_contract_failures,
                "trade_attempts": bot.trade_attempts,
                "trade_successes": bot.trade_successes,
                "trade_failures": bot.trade_failures,
                "trade_failure_reasons": bot.trade_failure_reasons,
                "action_counters": bot.action_counters,
                "recovery_actions": bot.recovery_actions,
                "sector": bot.sector,
                "credits": bot.credits,
                "turns_executed": bot.turns_executed,
                "started_at": bot.started_at,
                "stopped_at": bot.stopped_at,
            }
        )

    # Add state change event
    if bot.last_update_time:
        events.append(
            {
                "timestamp": bot.last_update_time,
                "type": "status_update",
                "state": bot.state,
                "activity": bot.activity_context,
                "status_detail": bot.status_detail,
                "sector": bot.sector,
                "credits": bot.credits,
                "turns_executed": bot.turns_executed,
                "strategy": bot.strategy,
                "strategy_id": bot.strategy_id,
                "strategy_mode": bot.strategy_mode,
                "strategy_intent": bot.strategy_intent,
                "llm_wakeups": bot.llm_wakeups,
                "autopilot_turns": bot.autopilot_turns,
                "goal_contract_failures": bot.goal_contract_failures,
                "trade_attempts": bot.trade_attempts,
                "trade_successes": bot.trade_successes,
                "trade_failures": bot.trade_failures,
                "trade_failure_reasons": bot.trade_failure_reasons,
                "action_counters": bot.action_counters,
                "recovery_actions": bot.recovery_actions,
                "llm_wakeups_per_100_turns": bot.llm_wakeups_per_100_turns,
                "hostile_fighters": bot.hostile_fighters,
                "under_attack": bot.under_attack,
                "started_at": bot.started_at,
                "stopped_at": bot.stopped_at,
            }
        )

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
        return JSONResponse({"error": f"Bot {bot_id} not found"}, status_code=404)

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
        return JSONResponse({"error": f"Failed to restart: {e}"}, status_code=500)
