# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Swarm manager for controlling multiple bot instances.

Provides central coordination for spawning, monitoring, and controlling
multiple trading bots through a REST API and WebSocket interface.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bbsbot.api import log_routes, swarm_routes, term_routes
from bbsbot.defaults import MANAGER_HOST, MANAGER_PORT
from bbsbot.log_service import LogService
from bbsbot.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from starlette.types import Scope


_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


class DashboardStaticFiles(StaticFiles):
    """Static files mount with no-store headers for dashboard frontend assets."""

    async def get_response(self, path: str, scope: Scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if path in {"dashboard.js"}:
            for key, value in _NO_STORE_HEADERS.items():
                response.headers[key] = value
        return response


class BotStatus(BaseModel):
    """Status of a single bot instance."""

    bot_id: str
    pid: int
    config: str
    state: str  # queued, running, completed, error, stopped
    sector: int = 0
    credits: int = -1  # -1 = uninitialized, 0+ = valid
    turns_executed: int = 0
    turns_max: int = 500  # Max turns for this session
    uptime_seconds: float = 0
    last_update_time: float = Field(default_factory=time.time)
    status_reported_at: float = 0.0  # worker-side event timestamp for stale update filtering
    completed_at: float | None = None  # Timestamp when bot completed
    started_at: float | None = None
    stopped_at: float | None = None
    error_message: str | None = None
    # Activity tracking
    last_action: str | None = None  # "TRADING", "EXPLORING", "BATTLING", etc
    last_action_time: float = 0  # timestamp of last action
    activity_context: str | None = None  # current game context
    status_detail: str | None = None  # phase/prompt detail (e.g., USERNAME, PAUSED, PORT_HAGGLE)
    prompt_id: str | None = None  # last detected prompt id (debugging/diagnostics)
    # Cargo tracking (best-effort from semantic extraction)
    cargo_fuel_ore: int | None = None
    cargo_organics: int | None = None
    cargo_equipment: int | None = None
    bank_balance: int = 0
    cargo_estimated_value: int = 0
    net_worth_estimate: int = 0
    # Error tracking
    error_type: str | None = None  # Exception class name (e.g., "TimeoutError")
    error_timestamp: float | None = None  # When error occurred
    exit_reason: str | None = None  # "target_reached", "out_of_turns", "login_failed", etc
    # Action feed (last 10 actions)
    recent_actions: list[dict] = Field(default_factory=list)
    # Character/game info for dashboard display
    username: str | None = None  # Character name
    # Strategy reporting is separate from on-screen context/prompt ids.
    # strategy_id: stable identifier (profitable_pairs/opportunistic/ai_strategy/...)
    # strategy_mode: conservative|balanced|aggressive (static or dynamic)
    # strategy_intent: short live "what I'm trying to do" string
    strategy: str | None = None  # Back-compat: UI display (usually "id(mode)")
    strategy_id: str | None = None
    strategy_mode: str | None = None
    strategy_intent: str | None = None
    ship_name: str | None = None  # Current ship name
    ship_level: str | None = None  # Ship class/level (Fighter, Trader, etc)
    port_location: int | None = None  # Current port sector
    # Trading telemetry (for strategy tuning / haggle diagnostics)
    haggle_accept: int = 0
    haggle_counter: int = 0
    haggle_too_high: int = 0
    haggle_too_low: int = 0
    trades_executed: int = 0
    credits_delta: int = 0
    credits_per_turn: float = 0.0
    llm_wakeups: int = 0
    autopilot_turns: int = 0
    goal_contract_failures: int = 0
    llm_wakeups_per_100_turns: float = 0.0
    # Hijack/MCP control tracking
    is_hijacked: bool = False  # Whether bot is under MCP control
    hijacked_at: float | None = None  # Timestamp when hijack started
    hijacked_by: str | None = None  # Who/what hijacked it (e.g., "mcp", "user")


class SwarmStatus(BaseModel):
    """Overall swarm status."""

    total_bots: int
    running: int
    completed: int
    errors: int
    stopped: int
    total_credits: int
    total_bank_credits: int = 0
    total_net_worth_estimate: int
    total_turns: int
    uptime_seconds: float
    timeseries_file: str | None = None
    timeseries_interval_seconds: int = 0
    timeseries_samples: int = 0
    bots: list[dict]


class SwarmManager:
    """Central manager for bot swarm."""

    def __init__(
        self,
        max_bots: int = 200,
        # Keep swarm state out of the repo root by default; sessions/ is gitignored.
        state_file: str = "sessions/swarm_state.json",
        health_check_interval: int = 10,
        timeseries_interval_s: int = 20,
        timeseries_dir: str = "logs/metrics",
    ):
        self.max_bots = max_bots
        self.state_file = state_file
        self.health_check_interval = health_check_interval
        self.start_time = time.time()
        self.timeseries_interval_s = max(1, int(timeseries_interval_s))
        self.timeseries_dir = Path(timeseries_dir)
        self.timeseries_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._timeseries_path = self.timeseries_dir / f"swarm_timeseries_{stamp}.jsonl"
        self._timeseries_samples = 0

        self.bots: dict[str, BotStatus] = {}
        self.processes: dict[str, subprocess.Popen] = {}
        self.websocket_clients: set[WebSocket] = set()
        self.log_service = LogService()
        # Track the current background spawn task so we can avoid overlapping spawns.
        self._spawn_task: asyncio.Task | None = None

        self.app = FastAPI(title="BBSBot Swarm Manager")
        self._setup_routes()
        self._setup_dashboard()
        self._load_state()

    async def cancel_spawn(self) -> bool:
        """Cancel any in-flight spawn batch.

        Without this, users can accidentally start multiple spawn batches, and `clear`
        won't actually clear because the old task keeps re-registering/spawning bots.
        """
        task = self._spawn_task
        if task is None or task.done():
            self._spawn_task = None
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        self._spawn_task = None
        return True

    async def start_spawn_swarm(
        self,
        config_paths: list[str],
        *,
        group_size: int = 1,
        group_delay: float = 12.0,
        cancel_existing: bool = True,
    ) -> None:
        """Start a background spawn batch (optionally canceling any existing batch)."""
        if cancel_existing:
            await self.cancel_spawn()
        self._spawn_task = asyncio.create_task(
            self.spawn_swarm(config_paths, group_size=group_size, group_delay=group_delay)
        )

    def _setup_dashboard(self) -> None:
        """Mount web dashboard static files and route."""
        web_dir = Path(__file__).parent / "web"
        static_dir = web_dir / "static"

        if static_dir.is_dir():
            self.app.mount(
                "/static",
                DashboardStaticFiles(directory=str(static_dir)),
                name="static",
            )

        dashboard_html = web_dir / "dashboard.html"

        @self.app.get("/", include_in_schema=False)
        async def dashboard_root():
            return RedirectResponse(url="/dashboard", status_code=307)

        @self.app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard():
            if dashboard_html.exists():
                return HTMLResponse(dashboard_html.read_text(), headers=_NO_STORE_HEADERS)
            return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)

    def _setup_routes(self) -> None:
        """Setup FastAPI routes via sub-routers and WebSocket."""
        self.app.include_router(swarm_routes.setup(self))
        self.app.include_router(log_routes.setup(self.log_service))
        self.app.include_router(term_routes.setup(self))

        @self.app.websocket("/ws/swarm")
        async def websocket_endpoint(websocket: WebSocket):
            """Real-time swarm updates."""
            await websocket.accept()
            self.websocket_clients.add(websocket)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.websocket_clients.remove(websocket)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.websocket_clients.discard(websocket)

    async def spawn_bot(self, config_path: str, bot_id: str) -> str:
        """Spawn a single bot process."""
        if len(self.bots) >= self.max_bots:
            raise RuntimeError(f"Max bots ({self.max_bots}) reached")

        if not Path(config_path).exists():
            raise RuntimeError(f"Config not found: {config_path}")

        logger.info(f"Spawning bot: {bot_id} with config {config_path}")

        # Spawn workers with the same interpreter as the manager process.
        # This avoids shell/PATH dependencies (e.g., missing `uv` under launchd).
        cmd = [
            sys.executable,
            "-m",
            "bbsbot.games.tw2002.worker",
            "--config",
            config_path,
            "--bot-id",
            bot_id,
        ]

        try:
            log_dir = Path("logs/workers")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{bot_id}.log"
            with log_file.open("w") as log_handle:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                )

            if bot_id in self.bots:
                # Update pre-registered queued bot
                self.bots[bot_id].pid = process.pid
                self.bots[bot_id].state = "running"
                self.bots[bot_id].last_update_time = time.time()
                self.bots[bot_id].started_at = time.time()
                self.bots[bot_id].stopped_at = None
            else:
                self.bots[bot_id] = BotStatus(
                    bot_id=bot_id,
                    pid=process.pid,
                    config=config_path,
                    state="running",
                    started_at=time.time(),
                )
            self.processes[bot_id] = process

            logger.info(f"Bot {bot_id} spawned with PID {process.pid}")
            await self._broadcast_status()
            return bot_id

        except Exception as e:
            logger.error(f"Failed to spawn bot {bot_id}: {e}")
            raise RuntimeError(f"Failed to spawn bot: {e}") from e

    async def spawn_swarm(
        self,
        config_paths: list[str],
        group_size: int = 5,
        group_delay: float = 60.0,
    ) -> list[str]:
        """Spawn multiple bots in staggered groups.

        Args:
            config_paths: List of config file paths for each bot.
            group_size: Number of bots to spawn simultaneously per group.
            group_delay: Seconds to wait between groups (allows logins to complete).
        """
        bot_ids = []
        total = len(config_paths)

        # Pre-register all bots as queued so they appear in dashboard immediately
        base_index = len(self.bots)
        for i, config in enumerate(config_paths):
            bot_id = f"bot_{base_index + i:03d}"
            if bot_id not in self.bots:
                self.bots[bot_id] = BotStatus(
                    bot_id=bot_id,
                    pid=0,
                    config=config,
                    state="queued",
                )
        await self._broadcast_status()

        for group_start in range(0, total, group_size):
            group_end = min(group_start + group_size, total)
            group_configs = config_paths[group_start:group_end]
            group_num = (group_start // group_size) + 1
            total_groups = (total + group_size - 1) // group_size

            logger.info(f"Spawning group {group_num}/{total_groups}: bots {group_start + 1}-{group_end} of {total}")

            # Spawn all bots in this group concurrently
            for i, config in enumerate(group_configs):
                bot_id = f"bot_{base_index + group_start + i:03d}"
                try:
                    await self.spawn_bot(config, bot_id)
                    bot_ids.append(bot_id)
                except Exception as e:
                    logger.error(f"Failed to spawn {bot_id} with {config}: {e}")

            # Wait between groups to let logins complete before next batch
            if group_end < total:
                logger.info(
                    f"Group {group_num} done ({len(group_configs)} spawned). "
                    f"Waiting {group_delay}s before next group..."
                )
                await asyncio.sleep(group_delay)

        logger.info(f"Swarm spawn complete: {len(bot_ids)}/{total} bots started")
        return bot_ids

    async def kill_bot(self, bot_id: str) -> None:
        """Terminate a bot process."""
        if bot_id not in self.processes:
            return

        process = self.processes[bot_id]
        try:
            process.terminate()
            process.wait(timeout=5)
            logger.info(f"Bot {bot_id} terminated")
        except subprocess.TimeoutExpired:
            process.kill()
            logger.warning(f"Bot {bot_id} force-killed")

        self.bots[bot_id].state = "stopped"
        self.bots[bot_id].stopped_at = time.time()
        del self.processes[bot_id]
        await self._broadcast_status()

    def get_swarm_status(self) -> SwarmStatus:
        """Get overall swarm metrics."""
        bots = list(self.bots.values())
        total_credits = sum(max(0, b.credits) for b in bots)
        total_bank_credits = sum(max(0, int(getattr(b, "bank_balance", 0) or 0)) for b in bots)
        total_net_worth = sum(
            max(
                0,
                int(
                    b.net_worth_estimate
                    if int(getattr(b, "net_worth_estimate", 0) or 0) > 0
                    else (
                        max(0, int(getattr(b, "credits", 0) or 0))
                        + max(0, int(getattr(b, "bank_balance", 0) or 0))
                        + max(0, int(getattr(b, "cargo_estimated_value", 0) or 0))
                    )
                ),
            )
            for b in bots
        )
        return SwarmStatus(
            total_bots=len(bots),
            # "recovering"/"blocked" are live workers; the dashboard's Running card
            # should reflect "alive", not just the narrow "running" state.
            running=sum(1 for b in bots if b.state in ("running", "recovering", "blocked")),
            completed=sum(1 for b in bots if b.state == "completed"),
            # "blocked" is an intentional non-terminal state (backoff + retry) but should
            # still be counted as an "error" metric for dashboard visibility.
            errors=sum(1 for b in bots if b.state in ("error", "disconnected", "blocked")),
            stopped=sum(1 for b in bots if b.state == "stopped"),
            # credits=-1 means "unknown/uninitialized"; don't let it poison totals.
            total_credits=total_credits,
            total_bank_credits=total_bank_credits,
            total_net_worth_estimate=total_net_worth,
            total_turns=sum(b.turns_executed for b in bots),
            uptime_seconds=time.time() - self.start_time,
            timeseries_file=str(self._timeseries_path),
            timeseries_interval_seconds=self.timeseries_interval_s,
            timeseries_samples=self._timeseries_samples,
            bots=[b.model_dump() for b in bots],
        )

    def get_timeseries_info(self) -> dict:
        """Get built-in timeseries metadata."""
        return {
            "path": str(self._timeseries_path),
            "interval_seconds": self.timeseries_interval_s,
            "samples": self._timeseries_samples,
        }

    def get_timeseries_recent(self, limit: int = 200) -> list[dict]:
        """Return recent built-in timeseries rows."""
        capped = max(1, min(int(limit), 5000))
        if not self._timeseries_path.exists():
            return []
        rows: deque[dict] = deque(maxlen=capped)
        with self._timeseries_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return list(rows)

    def get_timeseries_summary(self, window_minutes: int = 120) -> dict:
        """Summarize built-in timeseries over a trailing time window."""
        minutes = max(1, min(int(window_minutes), 24 * 60))
        if not self._timeseries_path.exists():
            return {
                "window_minutes": minutes,
                "rows": 0,
                "error": "timeseries file does not exist",
                "path": str(self._timeseries_path),
            }

        now = time.time()
        cutoff = now - (minutes * 60)
        window_rows: list[dict] = []
        with self._timeseries_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = float(row.get("ts") or 0)
                if ts >= cutoff:
                    window_rows.append(row)

        if not window_rows:
            return {
                "window_minutes": minutes,
                "rows": 0,
                "path": str(self._timeseries_path),
                "message": "no rows in selected window",
            }

        first = window_rows[0]
        last = window_rows[-1]

        def _safe_int(obj: dict, key: str) -> int:
            try:
                return int(obj.get(key) or 0)
            except Exception:
                return 0

        def _rolling_counter_delta(field: str) -> int:
            total = 0
            prev = _safe_int(window_rows[0], field)
            for row in window_rows[1:]:
                cur = _safe_int(row, field)
                # Reset-aware counter deltas (clear/restart can reset to 0).
                total += (cur - prev) if cur >= prev else cur
                prev = cur
            return total

        def _rolling_nested_counter_delta(parent: str, field: str) -> int:
            total = 0
            prev = int((window_rows[0].get(parent) or {}).get(field) or 0)
            for row in window_rows[1:]:
                cur = int((row.get(parent) or {}).get(field) or 0)
                total += (cur - prev) if cur >= prev else cur
                prev = cur
            return total

        def _strategy_deltas(field: str) -> dict[str, int]:
            out: dict[str, int] = {}
            prev_map: dict[str, int] = {}
            first_map = window_rows[0].get("trade_outcomes_by_strategy_mode") or {}
            for key, val in first_map.items():
                prev_map[key] = int((val or {}).get(field) or 0)

            for row in window_rows[1:]:
                cur_map = row.get("trade_outcomes_by_strategy_mode") or {}
                keys = set(prev_map.keys()) | set(cur_map.keys())
                for key in keys:
                    prev = int(prev_map.get(key, 0))
                    cur = int((cur_map.get(key) or {}).get(field) or 0)
                    out[key] = int(out.get(key, 0)) + ((cur - prev) if cur >= prev else cur)
                    prev_map[key] = cur

            return out

        def _strategy_avg_cpt() -> dict[str, float]:
            buckets: dict[str, list[float]] = {}
            for bot in (last.get("bots") or []):
                sid = str(bot.get("strategy_id") or "unknown")
                mode = str(bot.get("strategy_mode") or "unknown")
                key = f"{sid}({mode})"
                cpt = float(bot.get("credits_per_turn") or 0.0)
                buckets.setdefault(key, []).append(cpt)
            out: dict[str, float] = {}
            for key, vals in buckets.items():
                if vals:
                    out[key] = float(sum(vals) / len(vals))
            return out

        elapsed_s = float(last.get("ts") or now) - float(first.get("ts") or now)
        delta_turns = _rolling_counter_delta("total_turns")
        delta_credits = _rolling_counter_delta("total_credits")
        delta_bank_credits = _rolling_counter_delta("total_bank_credits")
        delta_net_worth = _rolling_counter_delta("total_net_worth_estimate")
        delta_llm_wakeups = _rolling_counter_delta("llm_wakeups_total")
        delta_trades = _rolling_nested_counter_delta("trade_outcomes_overall", "trades_executed")

        strategy_delta_trades = _strategy_deltas("trades_executed")
        strategy_delta_turns = _strategy_deltas("turns_executed")
        strategy_trades_per_100_turns: dict[str, float] = {}
        for key in set(strategy_delta_trades.keys()) | set(strategy_delta_turns.keys()):
            t = int(strategy_delta_trades.get(key, 0))
            u = int(strategy_delta_turns.get(key, 0))
            strategy_trades_per_100_turns[key] = (float(t) * 100.0 / float(u)) if u > 0 else 0.0

        return {
            "window_minutes": minutes,
            "rows": len(window_rows),
            "path": str(self._timeseries_path),
            "first_ts": first.get("ts"),
            "last_ts": last.get("ts"),
            "elapsed_seconds": elapsed_s,
            "delta": {
                "turns": delta_turns,
                "credits": delta_credits,
                "bank_credits": delta_bank_credits,
                "credits_per_turn": (float(delta_credits) / float(delta_turns)) if delta_turns > 0 else 0.0,
                "net_worth_estimate": delta_net_worth,
                "net_worth_per_turn": (float(delta_net_worth) / float(delta_turns)) if delta_turns > 0 else 0.0,
                "trades_executed": delta_trades,
                "trades_per_100_turns": (float(delta_trades) * 100.0 / float(delta_turns)) if delta_turns > 0 else 0.0,
                "haggle_offers": _rolling_nested_counter_delta("trade_outcomes_overall", "haggle_offers"),
                "llm_wakeups": delta_llm_wakeups,
                "llm_wakeups_per_100_turns": (
                    (float(delta_llm_wakeups) * 100.0 / float(delta_turns)) if delta_turns > 0 else 0.0
                ),
            },
            "last": {
                "running": _safe_int(last, "running"),
                "errors": _safe_int(last, "errors"),
                "trading_bots": _safe_int(last, "trading_bots"),
                "profitable_bots": _safe_int(last, "profitable_bots"),
                "positive_cpt_bots": _safe_int(last, "positive_cpt_bots"),
                "no_trade_120p": _safe_int(last, "no_trade_120p"),
                "total_credits": _safe_int(last, "total_credits"),
                "total_bank_credits": _safe_int(last, "total_bank_credits"),
                "total_net_worth_estimate": _safe_int(last, "total_net_worth_estimate"),
                "llm_wakeups_total": _safe_int(last, "llm_wakeups_total"),
                "autopilot_turns_total": _safe_int(last, "autopilot_turns_total"),
                "goal_contract_failures_total": _safe_int(last, "goal_contract_failures_total"),
                "llm_wakeups_per_100_turns": float(last.get("llm_wakeups_per_100_turns") or 0.0),
                "trade_outcomes_overall": last.get("trade_outcomes_overall") or {},
            },
            "strategy_delta": {
                "trades_executed": strategy_delta_trades,
                "turns_executed": strategy_delta_turns,
                "trades_per_100_turns": strategy_trades_per_100_turns,
                "haggle_accept": _strategy_deltas("haggle_accept"),
                "haggle_counter": _strategy_deltas("haggle_counter"),
                "haggle_too_high": _strategy_deltas("haggle_too_high"),
                "haggle_too_low": _strategy_deltas("haggle_too_low"),
                "avg_cpt_last": _strategy_avg_cpt(),
            },
        }

    def _build_timeseries_row(self, status: SwarmStatus, reason: str) -> dict:
        """Build one built-in timeseries sample row."""
        bots = status.bots
        state_counts: dict[str, int] = {}
        trading_bots = 0
        profitable_bots = 0
        positive_cpt_bots = 0
        no_trade_120p = 0
        haggle_low_total = 0
        haggle_high_total = 0
        llm_wakeups_total = 0
        autopilot_turns_total = 0
        goal_contract_failures_total = 0
        trade_outcomes_overall = {
            "trades_executed": 0,
            "haggle_accept": 0,
            "haggle_counter": 0,
            "haggle_too_high": 0,
            "haggle_too_low": 0,
        }
        trade_outcomes_by_strategy_mode: dict[str, dict] = {}
        bot_rows = []

        for bot in bots:
            state = str(bot.get("state") or "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1

            activity = str(bot.get("activity_context") or "").upper()
            if any(token in activity for token in ("TRAD", "PORT", "HAGGLE", "SHOP")):
                trading_bots += 1

            credits_delta = int(bot.get("credits_delta") or 0)
            if credits_delta > 0:
                profitable_bots += 1

            cpt = float(bot.get("credits_per_turn") or 0.0)
            if cpt > 0:
                positive_cpt_bots += 1

            trades = int(bot.get("trades_executed") or 0)
            turns = int(bot.get("turns_executed") or 0)
            if trades == 0 and turns >= 120:
                no_trade_120p += 1

            low = int(bot.get("haggle_too_low") or 0)
            high = int(bot.get("haggle_too_high") or 0)
            accept = int(bot.get("haggle_accept") or 0)
            counter = int(bot.get("haggle_counter") or 0)
            llm_wakeups = int(bot.get("llm_wakeups") or 0)
            autopilot_turns = int(bot.get("autopilot_turns") or 0)
            goal_contract_failures = int(bot.get("goal_contract_failures") or 0)
            haggle_low_total += low
            haggle_high_total += high
            llm_wakeups_total += llm_wakeups
            autopilot_turns_total += autopilot_turns
            goal_contract_failures_total += goal_contract_failures

            trade_outcomes_overall["trades_executed"] += trades
            trade_outcomes_overall["turns_executed"] = int(trade_outcomes_overall.get("turns_executed") or 0) + turns
            trade_outcomes_overall["haggle_accept"] += accept
            trade_outcomes_overall["haggle_counter"] += counter
            trade_outcomes_overall["haggle_too_high"] += high
            trade_outcomes_overall["haggle_too_low"] += low

            strategy_id = str(bot.get("strategy_id") or bot.get("strategy") or "unknown")
            strategy_mode = str(bot.get("strategy_mode") or "unknown")
            strategy_key = f"{strategy_id}({strategy_mode})"
            if strategy_key not in trade_outcomes_by_strategy_mode:
                trade_outcomes_by_strategy_mode[strategy_key] = {
                    "strategy_id": strategy_id,
                    "strategy_mode": strategy_mode,
                    "bots": 0,
                    "trades_executed": 0,
                    "turns_executed": 0,
                    "haggle_accept": 0,
                    "haggle_counter": 0,
                    "haggle_too_high": 0,
                    "haggle_too_low": 0,
                }
            strat = trade_outcomes_by_strategy_mode[strategy_key]
            strat["bots"] += 1
            strat["trades_executed"] += trades
            strat["turns_executed"] += turns
            strat["haggle_accept"] += accept
            strat["haggle_counter"] += counter
            strat["haggle_too_high"] += high
            strat["haggle_too_low"] += low

            bot_rows.append(
                {
                    "bot_id": bot.get("bot_id"),
                    "state": state,
                    "activity": bot.get("activity_context"),
                    "status": bot.get("status_detail"),
                    "sector": int(bot.get("sector") or 0),
                    "credits": int(bot.get("credits") or 0),
                    "bank_balance": int(bot.get("bank_balance") or 0),
                    "cargo_estimated_value": int(bot.get("cargo_estimated_value") or 0),
                    "net_worth_estimate": int(bot.get("net_worth_estimate") or 0),
                    "turns": turns,
                    "trades": trades,
                    "trades_per_100_turns": (float(trades) * 100.0 / float(turns)) if turns > 0 else 0.0,
                    "credits_delta": credits_delta,
                    "credits_per_turn": cpt,
                    "strategy_id": bot.get("strategy_id"),
                    "strategy_mode": bot.get("strategy_mode"),
                    "haggle_accept": accept,
                    "haggle_counter": counter,
                    "haggle_too_low": low,
                    "haggle_too_high": high,
                    "llm_wakeups": llm_wakeups,
                    "autopilot_turns": autopilot_turns,
                    "goal_contract_failures": goal_contract_failures,
                    "llm_wakeups_per_100_turns": float(bot.get("llm_wakeups_per_100_turns") or 0.0),
                }
            )

        overall_offers = (
            trade_outcomes_overall["haggle_accept"]
            + trade_outcomes_overall["haggle_counter"]
            + trade_outcomes_overall["haggle_too_high"]
            + trade_outcomes_overall["haggle_too_low"]
        )
        trade_outcomes_overall["haggle_offers"] = overall_offers
        trade_outcomes_overall["accept_rate"] = (
            float(trade_outcomes_overall["haggle_accept"]) / float(overall_offers) if overall_offers > 0 else 0.0
        )
        trade_outcomes_overall["too_high_rate"] = (
            float(trade_outcomes_overall["haggle_too_high"]) / float(overall_offers) if overall_offers > 0 else 0.0
        )
        trade_outcomes_overall["too_low_rate"] = (
            float(trade_outcomes_overall["haggle_too_low"]) / float(overall_offers) if overall_offers > 0 else 0.0
        )
        overall_turns = int(trade_outcomes_overall.get("turns_executed") or 0)
        trade_outcomes_overall["trades_per_100_turns"] = (
            (float(trade_outcomes_overall["trades_executed"]) * 100.0 / float(overall_turns)) if overall_turns > 0 else 0.0
        )

        for strat in trade_outcomes_by_strategy_mode.values():
            offers = strat["haggle_accept"] + strat["haggle_counter"] + strat["haggle_too_high"] + strat["haggle_too_low"]
            strat["haggle_offers"] = offers
            strat["accept_rate"] = float(strat["haggle_accept"]) / float(offers) if offers > 0 else 0.0
            strat["too_high_rate"] = float(strat["haggle_too_high"]) / float(offers) if offers > 0 else 0.0
            strat["too_low_rate"] = float(strat["haggle_too_low"]) / float(offers) if offers > 0 else 0.0
            strat_turns = int(strat.get("turns_executed") or 0)
            strat["trades_per_100_turns"] = (
                (float(strat["trades_executed"]) * 100.0 / float(strat_turns)) if strat_turns > 0 else 0.0
            )

        return {
            "ts": time.time(),
            "reason": reason,
            "uptime_seconds": status.uptime_seconds,
            "total_bots": status.total_bots,
            "running": status.running,
            "completed": status.completed,
            "errors": status.errors,
            "stopped": status.stopped,
            "total_credits": status.total_credits,
            "total_bank_credits": status.total_bank_credits,
            "total_net_worth_estimate": status.total_net_worth_estimate,
            "total_turns": status.total_turns,
            "state_counts": state_counts,
            "trading_bots": trading_bots,
            "profitable_bots": profitable_bots,
            "positive_cpt_bots": positive_cpt_bots,
            "no_trade_120p": no_trade_120p,
            "haggle_low_total": haggle_low_total,
            "haggle_high_total": haggle_high_total,
            "llm_wakeups_total": llm_wakeups_total,
            "autopilot_turns_total": autopilot_turns_total,
            "goal_contract_failures_total": goal_contract_failures_total,
            "llm_wakeups_per_100_turns": (
                (float(llm_wakeups_total) * 100.0 / float(status.total_turns)) if status.total_turns > 0 else 0.0
            ),
            "trade_outcomes_overall": trade_outcomes_overall,
            "trade_outcomes_by_strategy_mode": trade_outcomes_by_strategy_mode,
            "bots": bot_rows,
        }

    def _write_timeseries_sample(self, *, reason: str) -> None:
        """Write one built-in timeseries sample."""
        try:
            status = self.get_swarm_status()
            row = self._build_timeseries_row(status, reason=reason)
            with self._timeseries_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
            self._timeseries_samples += 1
        except Exception as e:
            logger.error(f"Failed to write swarm timeseries sample: {e}")

    async def _timeseries_loop(self) -> None:
        """Continuously write built-in swarm timeseries samples."""
        self._write_timeseries_sample(reason="startup")
        while True:
            await asyncio.sleep(self.timeseries_interval_s)
            self._write_timeseries_sample(reason="interval")

    async def _monitor_processes(self) -> None:
        """Monitor bot processes for crashes or completion."""
        while True:
            for bot_id, process in list(self.processes.items()):
                if process.poll() is not None:
                    exit_code = process.returncode
                    logger.warning(f"Bot {bot_id} exited with code {exit_code}")
                    bot = self.bots[bot_id]
                    if exit_code == 0:
                        # If the worker reported an error before exiting, preserve it.
                        # Otherwise "clean exit" can incorrectly look like success.
                        if bot.state == "error" or bot.error_message:
                            bot.state = "error"
                            if not bot.exit_reason:
                                bot.exit_reason = "reported_error_then_exit_0"
                        else:
                            bot.state = "completed"
                            bot.completed_at = time.time()
                            bot.stopped_at = time.time()
                            if not bot.exit_reason:
                                bot.exit_reason = "target_reached"
                    else:
                        bot.state = "error"
                        if not bot.exit_reason:
                            bot.exit_reason = f"exit_code_{exit_code}"
                        if not bot.error_message:
                            bot.error_message = f"Process exited with code {exit_code}"
                        bot.stopped_at = time.time()
                    del self.processes[bot_id]
                    await self._broadcast_status()

            now = time.time()
            for bot in self.bots.values():
                if bot.state in ("running",) and now - bot.last_update_time > 60:
                    logger.warning(f"Bot {bot.bot_id} heartbeat timeout (no status update in 60s)")
                    bot.state = "error"
                    bot.error_message = "No heartbeat in 60s - bot process may have crashed or is stuck"
                    bot.error_type = "HeartbeatTimeout"
                    bot.exit_reason = "heartbeat_timeout"
                    import time as time_module

                    bot.error_timestamp = time_module.time()
                    bot.stopped_at = time.time()

            await asyncio.sleep(self.health_check_interval)

    async def _broadcast_status(self) -> None:
        """Broadcast status to all connected WebSocket clients."""
        status = self.get_swarm_status()
        message = json.dumps(status.model_dump())

        disconnected = set()
        for client in self.websocket_clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.add(client)

        self.websocket_clients -= disconnected

    def _save_state(self) -> None:
        """Save swarm state to file."""
        state = {
            "timestamp": time.time(),
            "bots": {bot_id: bot.model_dump() for bot_id, bot in self.bots.items()},
        }
        with Path(self.state_file).open("w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self) -> None:
        """Load swarm state from file if exists."""
        if not Path(self.state_file).exists():
            return
        try:
            with Path(self.state_file).open() as f:
                state = json.load(f)
                # Load bots from previous state
                for bot_id, bot_data in state.get("bots", {}).items():
                    if bot_id not in self.bots:
                        # Loaded bots have no process handle - if they were
                        # "running" before the manager crashed, mark them
                        # "stopped" since we can't verify their actual state.
                        saved_state = bot_data.get("state", "stopped")
                        if saved_state in ("running", "disconnected"):
                            saved_state = "stopped"
                        # Reconstruct BotStatus from saved data
                        self.bots[bot_id] = BotStatus(
                            bot_id=bot_data.get("bot_id", bot_id),
                            pid=bot_data.get("pid", 0),
                            config=bot_data.get("config", ""),
                            state=saved_state,
                            sector=bot_data.get("sector", 0),
                            credits=bot_data.get("credits", 0),
                            turns_executed=bot_data.get("turns_executed", 0),
                            turns_max=bot_data.get("turns_max", 500),
                            uptime_seconds=bot_data.get("uptime_seconds", 0),
                            last_update_time=bot_data.get("last_update_time", time.time()),
                            completed_at=bot_data.get("completed_at"),
                            started_at=bot_data.get("started_at"),
                            stopped_at=bot_data.get("stopped_at"),
                            error_message=bot_data.get("error_message"),
                            last_action=bot_data.get("last_action"),
                            last_action_time=bot_data.get("last_action_time", 0),
                            activity_context=bot_data.get("activity_context"),
                            error_type=bot_data.get("error_type"),
                            error_timestamp=bot_data.get("error_timestamp"),
                            exit_reason=bot_data.get("exit_reason"),
                            recent_actions=bot_data.get("recent_actions", []),
                            username=bot_data.get("username"),
                            strategy=bot_data.get("strategy"),
                            strategy_id=bot_data.get("strategy_id"),
                            strategy_mode=bot_data.get("strategy_mode"),
                            strategy_intent=bot_data.get("strategy_intent"),
                            ship_name=bot_data.get("ship_name"),
                            ship_level=bot_data.get("ship_level"),
                            port_location=bot_data.get("port_location"),
                            cargo_fuel_ore=bot_data.get("cargo_fuel_ore"),
                            cargo_organics=bot_data.get("cargo_organics"),
                            cargo_equipment=bot_data.get("cargo_equipment"),
                            cargo_estimated_value=bot_data.get("cargo_estimated_value", 0),
                            net_worth_estimate=bot_data.get("net_worth_estimate", 0),
                            haggle_accept=bot_data.get("haggle_accept", 0),
                            haggle_counter=bot_data.get("haggle_counter", 0),
                            haggle_too_high=bot_data.get("haggle_too_high", 0),
                            haggle_too_low=bot_data.get("haggle_too_low", 0),
                            trades_executed=bot_data.get("trades_executed", 0),
                            credits_delta=bot_data.get("credits_delta", 0),
                            credits_per_turn=bot_data.get("credits_per_turn", 0.0),
                            llm_wakeups=bot_data.get("llm_wakeups", 0),
                            autopilot_turns=bot_data.get("autopilot_turns", 0),
                            goal_contract_failures=bot_data.get("goal_contract_failures", 0),
                            llm_wakeups_per_100_turns=bot_data.get("llm_wakeups_per_100_turns", 0.0),
                        )
                logger.info(f"Loaded {len(state.get('bots', {}))} bots from {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    async def run(self, host: str = MANAGER_HOST, port: int = MANAGER_PORT):
        """Run the manager server."""
        logger.info(f"Starting swarm manager on {host}:{port}")

        asyncio.create_task(self._monitor_processes())
        asyncio.create_task(self._timeseries_loop())

        async def save_periodically():
            while True:
                await asyncio.sleep(60)
                self._save_state()

        asyncio.create_task(save_periodically())

        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()


if __name__ == "__main__":
    manager = SwarmManager()
    asyncio.run(manager.run())
