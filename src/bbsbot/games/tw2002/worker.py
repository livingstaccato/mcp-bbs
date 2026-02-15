# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Bot worker process entry point for swarm management.

Runs a single bot instance and reports status to swarm manager.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import random
import string
import time
from collections import deque
from pathlib import Path

import click
import httpx

from bbsbot.defaults import MANAGER_URL as MANAGER_URL_DEFAULT
from bbsbot.games.tw2002.account_pool_store import AccountLeaseError, AccountPoolStore
from bbsbot.games.tw2002.bot import TradingBot
from bbsbot.games.tw2002.bot_identity_store import BotIdentityStore
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.logging import get_logger

logger = get_logger(__name__)


def _auto_username_from_bot_id(bot_id: str) -> str:
    base = "".join(ch for ch in bot_id if ch.isalnum()).lower()
    base = base[:8] if base else "bot"
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"{base}{suffix}"


def _resolve_worker_identity(
    *,
    bot_id: str,
    config_dict: dict,
    config_obj: BotConfig,
    identity_store: BotIdentityStore,
    account_pool: AccountPoolStore,
    config_path: Path,
) -> tuple[str, str, str, str]:
    """Resolve username/passwords with durable per-bot reuse."""
    identity = identity_store.load(bot_id)
    explicit_conn = (config_dict or {}).get("connection", {}) or {}
    explicit_char = (config_dict or {}).get("character", {}) or {}

    explicit_username = explicit_conn.get("username")
    explicit_game_pw = explicit_conn.get("game_password")
    explicit_char_pw = explicit_conn.get("character_password")
    explicit_char_cfg_pw = explicit_char.get("password")

    host = config_obj.connection.host
    port = config_obj.connection.port
    game_letter = config_obj.connection.game_letter

    explicit_mode = bool(explicit_username or config_obj.connection.username)
    identity_source = "unknown"

    preferred_username = (
        explicit_username or config_obj.connection.username or (identity.username if identity and identity.username else None)
    )
    preferred_char_pw = (
        explicit_char_pw
        or explicit_char_cfg_pw
        or (identity.character_password if identity and identity.character_password else None)
    )
    preferred_game_pw = (
        explicit_game_pw
        or (identity.game_password if identity and identity.game_password else None)
        or config_obj.connection.game_password
        or "game"
    )

    leased = None
    if preferred_username:
        try:
            identity_source = "config" if explicit_mode else "persisted"
            if (
                not explicit_mode
                and identity
                and identity.identity_source
                and identity.identity_source != "unknown"
            ):
                identity_source = identity.identity_source
            leased = account_pool.reserve_account(
                bot_id=bot_id,
                username=preferred_username,
                character_password=preferred_char_pw or preferred_username,
                game_password=preferred_game_pw,
                host=host,
                port=port,
                game_letter=game_letter,
                source=identity_source,
            )
        except AccountLeaseError:
            if explicit_mode:
                raise
            leased = account_pool.acquire_account(
                bot_id=bot_id,
                host=host,
                port=port,
                game_letter=game_letter,
            )
            if leased is not None:
                identity_source = "pool"
    else:
        leased = account_pool.acquire_account(
            bot_id=bot_id,
            host=host,
            port=port,
            game_letter=game_letter,
        )
        if leased is not None:
            identity_source = "pool"

    if leased is not None:
        username = leased.username
        character_password = leased.character_password
        game_password = leased.game_password or preferred_game_pw
    else:
        username = _auto_username_from_bot_id(bot_id)
        character_password = preferred_char_pw or username
        game_password = preferred_game_pw
        identity_source = "generated"
        account_pool.reserve_account(
            bot_id=bot_id,
            username=username,
            character_password=character_password,
            game_password=game_password,
            host=host,
            port=port,
            game_letter=game_letter,
            source=identity_source,
        )

    identity_store.upsert_identity(
        bot_id=bot_id,
        username=username,
        character_password=character_password,
        game_password=game_password,
        host=host,
        port=port,
        game_letter=game_letter,
        config_path=str(config_path),
        identity_source=identity_source,
    )
    return username, character_password, game_password, identity_source


class WorkerBot(TradingBot):
    """Bot worker with manager communication."""

    def __init__(self, bot_id: str, config: BotConfig, manager_url: str):
        """Initialize worker bot.

        Args:
            bot_id: Unique bot identifier
            config: Bot configuration
            manager_url: URL of swarm manager
        """
        super().__init__(character_name=bot_id, config=config)
        self.bot_id = bot_id
        self.manager_url = manager_url
        self.swarm_role = str(os.getenv("BBSBOT_SWARM_ROLE", "")).strip().lower() or None
        self._http_client = httpx.AsyncClient(timeout=10)
        # Activity tracking
        self.current_action: str | None = None
        self.current_action_time: float = 0
        self.recent_actions: list[dict] = []
        self.ai_activity: str | None = None  # AI reasoning for dashboard
        # Hijack support (paused automation only; Session reader pump always runs)
        self._hijacked: bool = False
        self._hijack_event: asyncio.Event = asyncio.Event()
        self._hijack_event.set()  # not hijacked by default
        # "Step" support: allow a bounded number of hijack checkpoints to pass.
        # The trading loop calls await_if_hijacked() twice per turn (top-of-loop + pre-action),
        # so one user "Step" grants 2 checkpoint passes by default.
        self._hijack_step_tokens: int = 0
        # Notify manager on screen changes so dashboard activity tracks screens.
        self._screen_change_event: asyncio.Event = asyncio.Event()
        self._screen_change_task: asyncio.Task | None = None
        self._last_seen_screen_hash: str = ""
        # Watchdog: if no progress is observed for too long, force a reconnect.
        self._watchdog_task: asyncio.Task | None = None
        self._last_progress_mono: float = time.monotonic()
        self._last_turns_seen: int = 0
        # Lifecycle state reported to manager (do not overwrite with "running" just because connected).
        self.lifecycle_state: str = "running"
        # Preserve last non-pause activity so pause screens don't overwrite Activity.
        self._last_activity_context: str | None = None
        # Trading telemetry (reported to manager/dashboard).
        self._session_start_credits: int | None = None
        self.haggle_accept: int = 0
        self.haggle_counter: int = 0
        self.haggle_too_high: int = 0
        self.haggle_too_low: int = 0
        self.trades_executed: int = 0
        self.trade_attempts: int = 0
        self.trade_successes: int = 0
        self.trade_failures: int = 0
        self.trade_failure_reasons: dict[str, int] = {}
        # Rich trade telemetry for per-port/per-resource diagnostics.
        self.trade_outcomes_by_port_resource: dict[str, dict[str, int]] = {}
        self.trade_outcomes_by_pair: dict[str, dict[str, int]] = {}
        # Prompt detection telemetry.
        self.prompt_telemetry: dict[str, int] = {}
        # Navigation/warp telemetry.
        self.warp_telemetry: dict[str, int] = {}
        self.warp_failure_reasons: dict[str, int] = {}
        # Decision pipeline telemetry.
        self.decisions_considered: dict[str, int] = {}
        self.decisions_executed: dict[str, int] = {}
        self.decision_override_reasons: dict[str, int] = {}
        self.decision_override_total: int = 0
        # Cargo valuation source/confidence telemetry.
        self.valuation_source_units_total: dict[str, int] = {}
        self.valuation_source_value_total: dict[str, int] = {}
        self.valuation_source_units_last: dict[str, int] = {}
        self.valuation_source_value_last: dict[str, int] = {}
        self.valuation_confidence_last: float = 0.0
        self._last_cargo_valuation_signature: tuple[tuple[str, int, str, int], ...] = ()
        self.action_counters: dict[str, int] = {}
        self.recovery_actions: int = 0
        self.combat_telemetry: dict[str, int] = {}
        self.attrition_telemetry: dict[str, int] = {}
        self.opportunity_telemetry: dict[str, int] = {}
        self.action_latency_telemetry: dict[str, int] = {}
        self.delta_attribution_telemetry: dict[str, int] = {}
        self.anti_collapse_runtime: dict[str, int | bool] = {}
        self.trade_quality_runtime: dict[str, int | float | bool] = {}
        self._last_hostile_fighters_seen: int = 0
        self._metrics_initialized: bool = False

    def reset_runtime_session_metrics(self) -> None:
        """Reset per-runtime-session metrics before a new login/run cycle."""
        self.turns_used = 0
        self._session_start_credits = None
        self.haggle_accept = 0
        self.haggle_counter = 0
        self.haggle_too_high = 0
        self.haggle_too_low = 0
        self.trades_executed = 0
        self.trade_attempts = 0
        self.trade_successes = 0
        self.trade_failures = 0
        self.trade_failure_reasons = {}
        self.trade_outcomes_by_port_resource = {}
        self.trade_outcomes_by_pair = {}
        self.prompt_telemetry = {}
        self.warp_telemetry = {}
        self.warp_failure_reasons = {}
        self.decisions_considered = {}
        self.decisions_executed = {}
        self.decision_override_reasons = {}
        self.decision_override_total = 0
        self.valuation_source_units_total = {}
        self.valuation_source_value_total = {}
        self.valuation_source_units_last = {}
        self.valuation_source_value_last = {}
        self.valuation_confidence_last = 0.0
        self._last_cargo_valuation_signature = ()
        self.action_counters = {}
        self.recovery_actions = 0
        self.combat_telemetry = {}
        self.attrition_telemetry = {}
        self.opportunity_telemetry = {}
        self.action_latency_telemetry = {}
        self.delta_attribution_telemetry = {}
        self.anti_collapse_runtime = {}
        self.trade_quality_runtime = {}
        self._last_hostile_fighters_seen = 0
        with contextlib.suppress(Exception):
            self._last_trade_turn = 0

    def note_trade_telemetry(self, metric: str, amount: int = 1) -> None:
        """Increment a trade telemetry counter in a safe, no-throw way."""
        try:
            if amount == 0:
                return
            if metric == "haggle_accept":
                self.haggle_accept = max(0, int(self.haggle_accept) + int(amount))
            elif metric == "haggle_counter":
                self.haggle_counter = max(0, int(self.haggle_counter) + int(amount))
            elif metric == "haggle_too_high":
                self.haggle_too_high = max(0, int(self.haggle_too_high) + int(amount))
            elif metric == "haggle_too_low":
                self.haggle_too_low = max(0, int(self.haggle_too_low) + int(amount))
            elif metric == "trades_executed":
                self.trades_executed = max(0, int(self.trades_executed) + int(amount))
            elif metric == "trade_attempts":
                self.trade_attempts = max(0, int(self.trade_attempts) + int(amount))
            elif metric == "trade_successes":
                self.trade_successes = max(0, int(self.trade_successes) + int(amount))
            elif metric == "trade_failures":
                self.trade_failures = max(0, int(self.trade_failures) + int(amount))
            elif metric.startswith("trade_fail_"):
                self.trade_failures = max(0, int(self.trade_failures) + int(amount))
                bucket = str(metric).strip().lower()
                if bucket:
                    prev = int(self.trade_failure_reasons.get(bucket, 0) or 0)
                    self.trade_failure_reasons[bucket] = max(0, prev + int(amount))
        except Exception:
            pass

    def note_trade_outcome(
        self,
        *,
        sector: int,
        commodity: str,
        side: str,
        success: bool,
        credit_change: int,
        failure_reason: str = "",
        pair_signature: str | None = None,
    ) -> None:
        """Record per-port/resource and per-pair trade outcomes."""
        try:
            sec = int(sector or 0)
            comm = str(commodity or "").strip().lower() or "unknown"
            if comm not in {"fuel_ore", "organics", "equipment", "all", "unknown"}:
                comm = "unknown"
            trade_side = str(side or "").strip().lower() or "unknown"
            if trade_side not in {"buy", "sell", "unknown"}:
                trade_side = "unknown"
            key = f"{sec}:{comm}:{trade_side}"
            bucket = self.trade_outcomes_by_port_resource.setdefault(
                key,
                {
                    "attempts": 0,
                    "successes": 0,
                    "failures": 0,
                    "credit_gain": 0,
                    "credit_loss": 0,
                    "zero_delta": 0,
                },
            )
            bucket["attempts"] = int(bucket.get("attempts", 0) or 0) + 1
            if success:
                bucket["successes"] = int(bucket.get("successes", 0) or 0) + 1
            else:
                bucket["failures"] = int(bucket.get("failures", 0) or 0) + 1
            delta = int(credit_change or 0)
            if delta > 0:
                bucket["credit_gain"] = int(bucket.get("credit_gain", 0) or 0) + delta
            elif delta < 0:
                bucket["credit_loss"] = int(bucket.get("credit_loss", 0) or 0) + abs(delta)
            else:
                bucket["zero_delta"] = int(bucket.get("zero_delta", 0) or 0) + 1
            if failure_reason:
                reason_key = f"fail_{str(failure_reason).strip().lower()}"
                bucket[reason_key] = int(bucket.get(reason_key, 0) or 0) + 1

            pair_key = str(pair_signature or "").strip().lower()
            if pair_key:
                pair_bucket = self.trade_outcomes_by_pair.setdefault(
                    pair_key,
                    {
                        "attempts": 0,
                        "successes": 0,
                        "failures": 0,
                        "credit_gain": 0,
                        "credit_loss": 0,
                        "zero_delta": 0,
                    },
                )
                pair_bucket["attempts"] = int(pair_bucket.get("attempts", 0) or 0) + 1
                if success:
                    pair_bucket["successes"] = int(pair_bucket.get("successes", 0) or 0) + 1
                else:
                    pair_bucket["failures"] = int(pair_bucket.get("failures", 0) or 0) + 1
                if delta > 0:
                    pair_bucket["credit_gain"] = int(pair_bucket.get("credit_gain", 0) or 0) + delta
                elif delta < 0:
                    pair_bucket["credit_loss"] = int(pair_bucket.get("credit_loss", 0) or 0) + abs(delta)
                else:
                    pair_bucket["zero_delta"] = int(pair_bucket.get("zero_delta", 0) or 0) + 1
        except Exception:
            return

    @staticmethod
    def _normalize_metric_key(metric: str, *, upper: bool = False) -> str:
        key = str(metric or "").strip()
        if not key:
            return ""
        return key.upper() if upper else key.lower()

    def _increment_map_counter(
        self,
        bucket: dict[str, int],
        key: str,
        amount: int = 1,
        *,
        upper: bool = False,
    ) -> None:
        token = self._normalize_metric_key(key, upper=upper)
        if not token:
            return
        prev = int(bucket.get(token, 0) or 0)
        bucket[token] = max(0, prev + int(amount))

    def note_prompt_telemetry(self, metric: str, amount: int = 1) -> None:
        try:
            self._increment_map_counter(self.prompt_telemetry, metric, amount)
        except Exception:
            return

    def note_warp_hop(self, *, success: bool, latency_ms: int, reason: str | None = None) -> None:
        try:
            self._increment_map_counter(self.warp_telemetry, "hops_attempted", 1)
            if success:
                self._increment_map_counter(self.warp_telemetry, "hops_succeeded", 1)
            else:
                self._increment_map_counter(self.warp_telemetry, "hops_failed", 1)
                if reason:
                    self._increment_map_counter(self.warp_failure_reasons, reason, 1)
            latency = max(0, int(latency_ms))
            self._increment_map_counter(self.warp_telemetry, "hop_latency_ms_sum", latency)
            prev_max = int(self.warp_telemetry.get("hop_latency_ms_max", 0) or 0)
            if latency > prev_max:
                self.warp_telemetry["hop_latency_ms_max"] = latency
        except Exception:
            return

    def note_decision_considered(self, action_name: str, amount: int = 1) -> None:
        try:
            self._increment_map_counter(
                self.decisions_considered,
                action_name,
                amount,
                upper=True,
            )
        except Exception:
            return

    def note_decision_executed(self, action_name: str, amount: int = 1) -> None:
        try:
            self._increment_map_counter(
                self.decisions_executed,
                action_name,
                amount,
                upper=True,
            )
        except Exception:
            return

    def note_decision_override(self, *, from_action: str, to_action: str, reason: str) -> None:
        try:
            from_key = self._normalize_metric_key(from_action, upper=True) or "UNKNOWN"
            to_key = self._normalize_metric_key(to_action, upper=True) or "UNKNOWN"
            reason_key = self._normalize_metric_key(reason) or "unknown"
            self.decision_override_total = max(0, int(self.decision_override_total) + 1)
            self._increment_map_counter(
                self.decision_override_reasons,
                f"{reason_key}:{from_key}->{to_key}",
                1,
            )
        except Exception:
            return

    def note_opportunity(self, metric: str, amount: int = 1) -> None:
        try:
            self._increment_map_counter(self.opportunity_telemetry, metric, amount)
        except Exception:
            return

    def note_action_latency(self, action_bucket: str, elapsed_ms: int) -> None:
        try:
            token = self._normalize_metric_key(action_bucket) or "unknown"
            self._increment_map_counter(self.action_latency_telemetry, f"{token}_count", 1)
            self._increment_map_counter(self.action_latency_telemetry, f"{token}_ms_sum", max(0, int(elapsed_ms)))
        except Exception:
            return

    def note_action_completion(
        self,
        *,
        action: str,
        credits_before: int,
        credits_after: int,
        bank_before: int,
        bank_after: int,
        cargo_before: dict[str, int],
        cargo_after: dict[str, int],
        trade_attempted: bool,
        trade_success: bool,
        combat_evidence: bool,
    ) -> None:
        """Attribution and combat/attrition telemetry from one completed action."""
        try:
            action_token = self._normalize_metric_key(action, upper=True) or "UNKNOWN"
            cred_delta = int(credits_after) - int(credits_before)
            bank_delta = int(bank_after) - int(bank_before)
            cargo_keys = ("fuel_ore", "organics", "equipment")
            cargo_net_delta = 0
            for key in cargo_keys:
                cargo_net_delta += int(cargo_after.get(key, 0) or 0) - int(cargo_before.get(key, 0) or 0)

            attribution: str | None = None
            if trade_attempted or action_token == "TRADE":
                attribution = "delta_trade"
            elif bank_delta != 0 or action_token == "BANK":
                attribution = "delta_bank"
            elif combat_evidence:
                attribution = "delta_combat"
            elif cred_delta != 0 or bank_delta != 0 or cargo_net_delta != 0:
                attribution = "delta_unknown"
            if attribution:
                self._increment_map_counter(self.delta_attribution_telemetry, attribution, 1)

            hostile_now = 0
            with contextlib.suppress(Exception):
                hostile_now = max(0, int(getattr(getattr(self, "game_state", None), "hostile_fighters", 0) or 0))
            if combat_evidence:
                self._increment_map_counter(self.combat_telemetry, "combat_context_seen", 1)
                self._increment_map_counter(self.combat_telemetry, "under_attack_reports", 1)
                if hostile_now > int(self._last_hostile_fighters_seen or 0):
                    self._increment_map_counter(self.combat_telemetry, "hostile_fighters_spike", 1)
            self._last_hostile_fighters_seen = max(0, int(hostile_now))

            screen_lower = ""
            with contextlib.suppress(Exception):
                if getattr(self, "session", None):
                    screen_lower = str(self.session.get_screen() or "").lower()
            if "escape pod" in screen_lower:
                self._increment_map_counter(self.combat_telemetry, "combat_prompt_escape_pod", 1)
            if "ferrengi" in screen_lower or "ferrengi fighter" in screen_lower:
                self._increment_map_counter(self.combat_telemetry, "combat_prompt_ferrengi", 1)
            if any(t in screen_lower for t in ("you have been destroyed", "you are dead", "killed by", "your ship was destroyed")):
                self._increment_map_counter(self.combat_telemetry, "death_prompt_detected", 1)
                self._increment_map_counter(self.combat_telemetry, "combat_destroyed", 1)
            if action_token == "RETREAT":
                self._increment_map_counter(self.combat_telemetry, "combat_retreats", 1)

            for key in cargo_keys:
                before = int(cargo_before.get(key, 0) or 0)
                after = int(cargo_after.get(key, 0) or 0)
                drop = max(0, before - after)
                if drop > 0 and (not trade_attempted):
                    self._increment_map_counter(self.attrition_telemetry, f"{key}_loss_nontrade", drop)
            if cred_delta < 0 and (not trade_success):
                self._increment_map_counter(self.attrition_telemetry, "credits_loss_nontrade", abs(int(cred_delta)))
        except Exception:
            return

    def _estimate_cargo_market_value(self, cargo: dict[str, int]) -> int:
        """Estimate liquidation value from observed market data (best-effort)."""
        knowledge = getattr(self, "sector_knowledge", None)
        sectors = (getattr(knowledge, "_sectors", {}) or {}) if knowledge else {}
        value_hints = getattr(self, "_cargo_value_hints", None)
        if not isinstance(value_hints, dict):
            value_hints = {}

        best_buy: dict[str, int] = {"fuel_ore": 0, "organics": 0, "equipment": 0}
        best_sell: dict[str, int] = {"fuel_ore": 0, "organics": 0, "equipment": 0}
        conservative_floor: dict[str, int] = {"fuel_ore": 15, "organics": 15, "equipment": 15}

        for info in sectors.values():
            prices = getattr(info, "port_prices", {}) or {}
            for commodity in ("fuel_ore", "organics", "equipment"):
                entry = prices.get(commodity) or {}
                with contextlib.suppress(Exception):
                    buy_unit = int(entry.get("buy") or 0)
                    if buy_unit > best_buy[commodity]:
                        best_buy[commodity] = buy_unit
                with contextlib.suppress(Exception):
                    sell_unit = int(entry.get("sell") or 0)
                    if sell_unit > best_sell[commodity]:
                        best_sell[commodity] = sell_unit

        total = 0
        source_units: dict[str, int] = {"quote": 0, "hint": 0, "sell_fallback": 0, "floor": 0}
        source_values: dict[str, int] = {"quote": 0, "hint": 0, "sell_fallback": 0, "floor": 0}
        confidence_for_source = {"quote": 1.0, "hint": 0.72, "sell_fallback": 0.45, "floor": 0.25}
        confidence_weighted = 0.0
        confidence_units = 0
        valuation_signature_parts: list[tuple[str, int, str, int]] = []
        for commodity, qty in cargo.items():
            if qty <= 0:
                continue
            unit = int(best_buy.get(commodity) or 0)
            source = "quote"
            if unit <= 0:
                with contextlib.suppress(Exception):
                    unit = max(unit, int(value_hints.get(commodity) or 0))
                if unit > 0:
                    source = "hint"
            # If we only know sell-side quotes, estimate a conservative liquidation value.
            if unit <= 0:
                fallback_sell = int(best_sell.get(commodity) or 0)
                unit = int(fallback_sell * 0.7) if fallback_sell > 0 else 0
                if unit > 0:
                    source = "sell_fallback"
            if unit <= 0:
                unit = int(conservative_floor.get(commodity, 0) or 0)
                source = "floor"
            qty_int = max(0, int(qty))
            unit_int = max(0, int(unit))
            line_value = qty_int * unit_int
            total += line_value
            source_units[source] = int(source_units.get(source, 0) or 0) + qty_int
            source_values[source] = int(source_values.get(source, 0) or 0) + line_value
            confidence_weighted += float(confidence_for_source.get(source, 0.0)) * float(qty_int)
            confidence_units += qty_int
            valuation_signature_parts.append((str(commodity), qty_int, source, unit_int))
        self.valuation_source_units_last = dict(source_units)
        self.valuation_source_value_last = dict(source_values)
        self.valuation_confidence_last = (
            float(confidence_weighted) / float(confidence_units)
            if confidence_units > 0
            else 0.0
        )

        signature = tuple(sorted(valuation_signature_parts))
        if signature != self._last_cargo_valuation_signature:
            self._last_cargo_valuation_signature = signature
            for key, value in source_units.items():
                self._increment_map_counter(self.valuation_source_units_total, key, int(value))
            for key, value in source_values.items():
                self._increment_map_counter(self.valuation_source_value_total, key, int(value))
        return int(total)

    def _note_progress(self) -> None:
        self._last_progress_mono = time.monotonic()

    def start_watchdog(self, *, stuck_timeout_s: float = 120.0, check_interval_s: float = 5.0) -> None:
        """Start a watchdog that forces recovery if the bot stops making progress.

        Progress signals:
        - turns_used increases
        - screen_hash changes

        If we see neither for `stuck_timeout_s`, we disconnect the session. The outer
        worker loop will reconnect + re-login + continue.
        """
        if self._watchdog_task is not None and not self._watchdog_task.done():
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(max(0.5, float(check_interval_s)))
                try:
                    if self._hijacked:
                        # If a human is driving, don't fight them.
                        self._note_progress()
                        continue

                    # Turns progression is authoritative for "still alive".
                    if self.turns_used != self._last_turns_seen:
                        self._last_turns_seen = self.turns_used
                        self._note_progress()

                    idle_for = time.monotonic() - self._last_progress_mono
                    if idle_for < float(stuck_timeout_s):
                        continue

                    # Stuck: report + force reconnect by disconnecting the session.
                    try:
                        self.ai_activity = f"WATCHDOG: STUCK ({int(idle_for)}s)"
                        await self.report_error(
                            RuntimeError(f"watchdog_stuck_{int(idle_for)}s"),
                            exit_reason="watchdog_stuck",
                            fatal=False,
                            state="recovering",
                        )
                        await self.report_status()
                    except Exception:
                        pass

                    with contextlib.suppress(Exception):
                        await self.disconnect()

                    # Reset timer so we don't spam disconnect loops if reconnect is slow.
                    self._note_progress()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    continue

        self._watchdog_task = asyncio.create_task(_loop())

    async def register_with_manager(self) -> None:
        """Register this bot with the swarm manager."""
        try:
            await self._http_client.post(
                f"{self.manager_url}/bot/{self.bot_id}/register",
                json={"pid": os.getpid()},
            )
            logger.info(f"Registered with manager: {self.bot_id}")
        except Exception as e:
            logger.warning(f"Failed to register with manager: {e}")

    async def report_status(self) -> None:
        """Report current status to manager."""
        try:
            # Always prefer game_state credits (source of truth) over cached current_credits
            # Fallback to current_credits only if game_state unavailable
            credits: int | None = None
            if self.game_state and self.game_state.credits is not None:
                credits = int(self.game_state.credits)
            elif getattr(self, "current_credits", 0) and int(self.current_credits) > 0:
                # current_credits defaults to 0; avoid claiming "0 credits" unless observed.
                credits = int(self.current_credits)
            else:
                # Fallback: semantic extraction from live screens (updated by session watcher / wait_and_respond).
                sem = getattr(self, "last_semantic_data", {}) or {}
                try:
                    sem_credits = sem.get("credits")
                    if sem_credits is not None:
                        credits = int(sem_credits)
                except Exception:
                    credits = None
            credits_out = int(credits) if credits is not None else -1
            sem = getattr(self, "last_semantic_data", {}) or {}
            try:
                # Default to 0 so the dashboard/TUI show stable numeric columns even
                # before we've visited a port table that includes OnBoard quantities.
                cargo_fuel_ore = int(sem.get("cargo_fuel_ore")) if sem.get("cargo_fuel_ore") is not None else 0
            except Exception:
                cargo_fuel_ore = 0
            try:
                cargo_organics = int(sem.get("cargo_organics")) if sem.get("cargo_organics") is not None else 0
            except Exception:
                cargo_organics = 0
            try:
                cargo_equipment = int(sem.get("cargo_equipment")) if sem.get("cargo_equipment") is not None else 0
            except Exception:
                cargo_equipment = 0
            hostile_fighters = 0
            try:
                if self.game_state and getattr(self.game_state, "hostile_fighters", None) is not None:
                    hostile_fighters = max(0, int(getattr(self.game_state, "hostile_fighters", 0) or 0))
                elif sem.get("hostile_fighters") is not None:
                    hostile_fighters = max(0, int(sem.get("hostile_fighters") or 0))
            except Exception:
                hostile_fighters = 0
            cargo_map = {
                "fuel_ore": int(cargo_fuel_ore),
                "organics": int(cargo_organics),
                "equipment": int(cargo_equipment),
            }
            bank_balance = 0
            # Prefer explicit semantic extraction when present (e.g., after bank screens).
            try:
                if sem.get("bank_balance") is not None:
                    bank_balance = max(0, int(sem.get("bank_balance")))
            except Exception:
                bank_balance = 0
            # Fallback to the banking manager's tracked balance.
            try:
                mgr = getattr(self, "_banking", None)
                if mgr is not None:
                    bank_balance = max(bank_balance, int(getattr(mgr, "bank_balance", 0) or 0))
            except Exception:
                pass
            cargo_estimated_value = self._estimate_cargo_market_value(cargo_map)
            net_worth_estimate = (
                max(0, int(credits_out if credits_out >= 0 else 0))
                + int(bank_balance)
                + int(cargo_estimated_value)
            )

            # Determine turns_max from config if available
            # 0 = auto-detect server maximum (persistent mode)
            turns_max = getattr(self.config, "session", {})
            turns_max = turns_max.max_turns_per_session if hasattr(turns_max, "max_turns_per_session") else 0

            # CRITICAL FIX: Use CURRENT screen for activity detection, not stale game_state
            # This ensures activity always matches what's actually on screen
            activity = "INITIALIZING"
            current_screen = ""
            current_context = "unknown"
            prompt_id: str | None = None
            screen_lower = ""
            is_command_prompt = False
            screen_phase: str | None = None
            in_game_now = False
            lifecycle_status: str | None = None

            # Get current screen from session
            if hasattr(self, "session") and self.session:
                try:
                    current_screen = self.session.get_screen()
                except Exception:
                    current_screen = ""
                try:
                    snap = self.session.snapshot() or {}
                    pd = snap.get("prompt_detected") or {}
                    if isinstance(pd, dict):
                        prompt_id = pd.get("prompt_id")
                except Exception:
                    prompt_id = None

            screen_lower = (current_screen or "").lower()
            # This is the only reliable "in game" indicator on this server.
            is_command_prompt = "command [tl=" in screen_lower
            in_game_now = bool(
                is_command_prompt
                or (self.current_sector and int(self.current_sector) > 0)
                or (self.game_state and getattr(self.game_state, "sector", 0))
                or (self.turns_used > 0)
            )

            def _screen_phase(s: str) -> str | None:
                """Best-effort phase classification from raw screen text."""
                if not s:
                    return None
                # Character creation
                if "use (n)ew name or (b)bs name" in s:
                    return "CREATING_CHARACTER"
                if "what do you want to name your ship" in s:
                    return "CREATING_CHARACTER"
                if "name your home planet" in s:
                    return "CREATING_CHARACTER"
                if "press enter to begin your adventure" in s:
                    return "CREATING_CHARACTER"
                if "gender (m/f)" in s:
                    return "CREATING_CHARACTER"
                if "please enter your name" in s and "enter for none" in s:
                    return "CREATING_CHARACTER"
                if "create new character" in s or "start a new character" in s:
                    return "CREATING_CHARACTER"
                # Password-related
                if "repeat password to verify" in s:
                    return "CHOOSING_PASSWORD"
                if "required to enter this game" in s or "private game" in s:
                    return "GAME_PASSWORD"
                if "password" in s and not is_command_prompt:
                    return "CHOOSING_PASSWORD"
                # Username/login
                if "login name" in s or "what is your name" in s:
                    return "USERNAME"
                return None

            screen_phase = _screen_phase(screen_lower)

            # Detect REAL-TIME context from current screen
            if current_screen.strip():
                from bbsbot.games.tw2002.orientation.detection import detect_context

                current_context = detect_context(current_screen)

                # Map detected context to human-readable activity
                if current_context == "sector_command":
                    activity = "EXPLORING"
                elif current_context in ("port_menu", "port_trading"):
                    activity = "TRADING"
                elif current_context in ("bank", "ship_shop", "hardware_shop"):
                    activity = "SHOPPING"
                elif current_context == "combat":
                    activity = "BATTLING"
                elif current_context == "corporate_listings":
                    activity = "CORPORATE_LISTINGS_MENU"
                elif current_context in ("planet_command", "citadel_command"):
                    activity = "ON_PLANET"
                elif current_context == "menu":
                    # Check if it's game selection menu (sector is None means not in game yet)
                    activity = "GAME_SELECTION_MENU" if not in_game_now else "IN_GAME_MENU"
                elif current_context == "pause":
                    # Keep Activity stable; show PAUSED in Status instead.
                    activity = self._last_activity_context or (
                        "IN_GAME" if (self.current_sector and self.current_sector > 0) else "LOGGING_IN"
                    )
                elif current_context == "unknown":
                    # Ambiguous snapshot: keep last known in-game activity when possible.
                    activity = self._last_activity_context or "IN_GAME" if in_game_now else "LOGGING_IN"
                else:
                    # Any other context, show it verbatim
                    activity = current_context.upper()
            else:
                # No screen content - must be connecting/disconnected
                if hasattr(self, "session") and self.session and self.session.is_connected():
                    activity = (self._last_activity_context or "IN_GAME") if in_game_now else "CONNECTING"
                else:
                    activity = self._last_activity_context or ("IN_GAME" if in_game_now else "LOGGING_IN")
                    lifecycle_status = "DISCONNECTED"

            # Prefer a concise "Status" field for phase/prompt detail, separate from activity.
            status_detail: str | None = None
            if lifecycle_status:
                status_detail = lifecycle_status
            if screen_phase:
                status_detail = screen_phase
                # Avoid mislabeling stale sector-derived states as "IN_GAME".
                if not is_command_prompt and not in_game_now:
                    activity = "LOGGING_IN"

            prompt_to_status = {
                # Login flows
                "prompt.login_name": "USERNAME",
                "prompt.what_is_your_name": "USERNAME",
                "prompt.character_name": "USERNAME",
                "prompt.game_password": "GAME_PASSWORD",
                "prompt.private_game_password": "GAME_PASSWORD",
                "prompt.game_password_plain": "GAME_PASSWORD",
                "prompt.game_selection": "GAME_SELECTION",
                "prompt.menu_selection": "MENU_SELECTION",
                # Character creation (server reset)
                "prompt.create_character": "CREATING_CHARACTER",
                "prompt.new_player_name": "CREATING_CHARACTER",
                "prompt.name_or_bbs": "CREATING_CHARACTER",
                "prompt.twgs_gender": "CREATING_CHARACTER",
                "prompt.twgs_real_name": "CREATING_CHARACTER",
                "prompt.twgs_ship_selection": "CREATING_CHARACTER",
                "prompt.twgs_begin_adventure": "CREATING_CHARACTER",
                "prompt.ship_name": "CREATING_CHARACTER",
                "prompt.planet_name": "CREATING_CHARACTER",
                # Password selection / entry
                # If we're not in-game yet, treat this as choosing/setting the character password.
                "prompt.character_password": "CHOOSING_PASSWORD",
                "prompt.corporate_listings": "CORPORATE_LISTINGS",
                # In-game prompts (only the blocking ones; don't show "SECTOR_COMMAND" etc.)
                "prompt.port_menu": "PORT_MENU",
                "prompt.hardware_buy": "PORT_QTY",
                "prompt.port_haggle": "PORT_HAGGLE",
                # Pause variants
                "prompt.pause_simple": "PAUSED",
                "prompt.pause_space_or_enter": "PAUSED",
            }
            login_statuses = {
                "USERNAME",
                "GAME_PASSWORD",
                "GAME_SELECTION",
                "CREATING_CHARACTER",
                "CHOOSING_PASSWORD",
            }
            if prompt_id:
                mapped = prompt_to_status.get(prompt_id)
                # Once in-game, do not regress status back to login phases.
                if mapped and not status_detail and not (in_game_now and mapped in login_statuses):
                    status_detail = mapped

            # If the password prompt is happening while already in-game, it's not password *selection*.
            if prompt_id == "prompt.character_password":
                in_game_now = bool(self.current_sector and self.current_sector > 0)
                if in_game_now:
                    status_detail = "PASSWORD"

            # Override activity for specific prompts that are more precise than context detection.
            if prompt_id == "prompt.stardock_buy":
                activity = "SHOPPING"

            # Surface combat/attack state explicitly for dashboard visibility.
            try:
                danger_threshold = int(getattr(self.config.combat, "danger_threshold", 100))
            except Exception:
                danger_threshold = 100
            under_attack = bool(current_context == "combat" or hostile_fighters > danger_threshold)
            if under_attack and not status_detail:
                status_detail = "UNDER_ATTACK"
            elif hostile_fighters > 0 and not status_detail and in_game_now:
                status_detail = f"THREAT:{hostile_fighters}"

            # Pause screens should show as Status, not Activity.
            if current_context == "pause":
                status_detail = "PAUSED"

            # Final safety: if we already know we're in-game, don't present LOGGING_IN.
            if in_game_now and activity in ("LOGGING_IN", "CONNECTING"):
                activity = self._last_activity_context or "IN_GAME"

            # Orient progress tracking for debugging (Status, not Activity).
            orient_step = getattr(self, "_orient_step", 0)
            orient_max = getattr(self, "_orient_max", 0)
            orient_phase = getattr(self, "_orient_phase", "")

            # CRITICAL: Do NOT override activity with "ORIENTING" if we know the context
            # Only show ORIENTING if context is actually "unknown"
            in_game = self.current_sector and self.current_sector > 0
            # Only surface orient progress when we don't already have a stronger
            # status signal (prompt/status_detail). This prevents stale
            # ORIENTING:FAILED from overriding active states like PORT_HAGGLE.
            if orient_phase and current_context == "unknown" and in_game and not status_detail:
                if orient_step > 0 and orient_max > 0:
                    status_detail = f"ORIENTING:{orient_step}/{orient_max}"
                else:
                    phase_names = {
                        "starting": "INIT",
                        "gather": "GATHER",
                        "safe_state": "SAFE_STATE",
                        "blank_wake": "WAKE",
                        "failed": "FAILED",
                    }
                    phase_display = phase_names.get(orient_phase, orient_phase.upper())
                    status_detail = f"ORIENTING:{phase_display}"

            # Extract character/ship info from game state
            username = None
            ship_level = None
            ship_name = None

            if self.game_state:
                username = getattr(self.game_state, "player_name", None) or self.character_name
                ship_level = getattr(self.game_state, "ship_type", None)
                ship_name = getattr(self.game_state, "ship_name", None)
            else:
                username = self.character_name

            # Strategy name for dashboard column (prefer live instance, fall back to config).
            try:
                strategy_name = getattr(getattr(self, "strategy", None), "name", None)
            except Exception:
                strategy_name = None
            if not strategy_name:
                try:
                    strategy_name = getattr(getattr(self, "config", None), "trading", None).strategy  # type: ignore[union-attr]
                except Exception:
                    strategy_name = None

            # Strategy policy/mode and intent are maintained by the trading loop.
            strategy_mode = getattr(self, "strategy_mode", None)
            strategy_intent = getattr(self, "strategy_intent", None)
            try:
                if not strategy_mode and self.strategy and hasattr(self.strategy, "policy"):
                    strategy_mode = getattr(self.strategy, "policy", None)
            except Exception:
                pass
            try:
                if not strategy_intent and self.strategy and hasattr(self.strategy, "intent"):
                    strategy_intent = getattr(self.strategy, "intent", None)
            except Exception:
                pass

            # Back-compat display string used by older dashboard rendering.
            strategy_display = strategy_name
            if strategy_name and strategy_mode in ("conservative", "balanced", "aggressive"):
                strategy_display = f"{strategy_name}({strategy_mode})"

            # Determine actual state from session connectivity
            connected = (
                hasattr(self, "session")
                and self.session is not None
                and hasattr(self.session, "is_connected")
                and self.session.is_connected()
            )
            # Preserve lifecycle state (recovering/blocked) across periodic status reports.
            actual_state = getattr(self, "lifecycle_state", "running") or "running"
            if actual_state == "running" and not connected:
                actual_state = "disconnected"
            if not connected:
                if not activity or activity in ("INITIALIZING", "CONNECTING", "DISCONNECTED"):
                    activity = self._last_activity_context or ("IN_GAME" if in_game_now else "LOGGING_IN")
                if not status_detail:
                    status_detail = "DISCONNECTED"

            # Check if AI strategy is thinking (waiting for LLM response).
            if self.strategy and hasattr(self.strategy, "_is_thinking") and self.strategy._is_thinking:
                status_detail = "THINKING"

            # Override with AI reasoning if available (Status, not Activity).
            if self.ai_activity:
                status_detail = self.ai_activity
                self.ai_activity = None  # Clear after reporting

            # Preserve last known sector across non-command screens (ports, menus, haggles).
            # Before first in-game detection this remains 0, which is expected.
            sector_out = 0
            try:
                if self.current_sector and int(self.current_sector) > 0:
                    sector_out = int(self.current_sector)
                elif self.game_state and getattr(self.game_state, "sector", None):
                    gs_sector = int(self.game_state.sector)
                    if gs_sector > 0:
                        sector_out = gs_sector
                elif sem.get("sector") is not None:
                    sem_sector = int(sem.get("sector"))
                    if sem_sector > 0:
                        sector_out = sem_sector
            except Exception:
                sector_out = 0

            # Build status update dict
            if credits_out >= 0 and self._session_start_credits is None:
                self._session_start_credits = credits_out
            credits_delta = 0
            if credits_out >= 0 and self._session_start_credits is not None:
                credits_delta = int(credits_out - self._session_start_credits)
            credits_per_turn = float(credits_delta) / float(self.turns_used) if self.turns_used > 0 else 0.0
            last_trade_turn = int(getattr(self, "_last_trade_turn", 0) or 0)
            turns_since_last_trade = int(self.turns_used) if last_trade_turn <= 0 else max(
                0,
                int(self.turns_used) - last_trade_turn,
            )
            move_streak = 0
            zero_delta_action_streak = 0
            for entry in reversed(list(self.recent_actions or [])):
                action_name = str(entry.get("action") or "").strip().upper()
                if action_name in {"MOVE", "EXPLORE"}:
                    move_streak += 1
                else:
                    break
            for entry in reversed(list(self.recent_actions or [])):
                try:
                    delta = int(entry.get("result_delta") or 0)
                except Exception:
                    delta = 0
                if delta == 0:
                    zero_delta_action_streak += 1
                else:
                    break

            status_data = {
                "reported_at": time.time(),
                "sector": sector_out,
                "turns_executed": self.turns_used,
                "turns_max": turns_max,
                "state": actual_state,
                "last_action": self.current_action,
                "last_action_time": self.current_action_time,
                "activity_context": activity,
                "status_detail": status_detail,
                "prompt_id": prompt_id,
                "strategy": strategy_display,
                "strategy_id": strategy_name,
                "strategy_mode": strategy_mode,
                "strategy_intent": strategy_intent,
                "swarm_role": self.swarm_role,
                "cargo_fuel_ore": cargo_fuel_ore,
                "cargo_organics": cargo_organics,
                "cargo_equipment": cargo_equipment,
                "bank_balance": int(bank_balance),
                "cargo_estimated_value": int(cargo_estimated_value),
                "net_worth_estimate": int(net_worth_estimate),
                "recent_actions": self.recent_actions[-10:],  # Last 10 actions
                "haggle_accept": int(self.haggle_accept),
                "haggle_counter": int(self.haggle_counter),
                "haggle_too_high": int(self.haggle_too_high),
                "haggle_too_low": int(self.haggle_too_low),
                "trades_executed": int(self.trades_executed),
                "trade_attempts": int(self.trade_attempts),
                "trade_successes": int(self.trade_successes),
                "trade_failures": int(self.trade_failures),
                "trade_failure_reasons": dict(self.trade_failure_reasons or {}),
                "trade_outcomes_by_port_resource": dict(self.trade_outcomes_by_port_resource or {}),
                "trade_outcomes_by_pair": dict(self.trade_outcomes_by_pair or {}),
                "credits_delta": int(credits_delta),
                "credits_per_turn": float(credits_per_turn),
                "turns_since_last_trade": int(turns_since_last_trade),
                "move_streak": int(move_streak),
                "zero_delta_action_streak": int(zero_delta_action_streak),
                "hostile_fighters": int(hostile_fighters),
                "under_attack": bool(under_attack),
                "action_counters": dict(self.action_counters or {}),
                "recovery_actions": int(self.recovery_actions),
                "combat_telemetry": dict(self.combat_telemetry or {}),
                "attrition_telemetry": dict(self.attrition_telemetry or {}),
                "opportunity_telemetry": dict(self.opportunity_telemetry or {}),
                "action_latency_telemetry": dict(self.action_latency_telemetry or {}),
                "delta_attribution_telemetry": dict(self.delta_attribution_telemetry or {}),
                "prompt_telemetry": dict(self.prompt_telemetry or {}),
                "warp_telemetry": dict(self.warp_telemetry or {}),
                "warp_failure_reasons": dict(self.warp_failure_reasons or {}),
                "decision_counts_considered": dict(self.decisions_considered or {}),
                "decision_counts_executed": dict(self.decisions_executed or {}),
                "decision_override_total": int(self.decision_override_total),
                "decision_override_reasons": dict(self.decision_override_reasons or {}),
                "valuation_source_units_total": dict(self.valuation_source_units_total or {}),
                "valuation_source_value_total": dict(self.valuation_source_value_total or {}),
                "valuation_source_units_last": dict(self.valuation_source_units_last or {}),
                "valuation_source_value_last": dict(self.valuation_source_value_last or {}),
                "valuation_confidence_last": float(self.valuation_confidence_last or 0.0),
            }
            if actual_state == "running":
                # Clear stale error banners once the bot has recovered and resumed.
                status_data["error_message"] = None
                status_data["error_type"] = None
                status_data["error_timestamp"] = None
            try:
                s_stats = self.strategy.stats if self.strategy else {}
            except Exception:
                s_stats = {}
            status_data["llm_wakeups"] = int(s_stats.get("llm_wakeups", 0) or 0)
            status_data["autopilot_turns"] = int(s_stats.get("autopilot_turns", 0) or 0)
            status_data["goal_contract_failures"] = int(s_stats.get("goal_contract_failures", 0) or 0)
            status_data["route_churn_total"] = int(s_stats.get("pair_invalidations_total", 0) or 0)
            status_data["route_churn_reasons"] = dict(s_stats.get("pair_invalidations_by_reason", {}) or {})
            anti_runtime = dict(s_stats.get("anti_collapse_runtime") or {})
            if anti_runtime:
                anti_runtime["forced_probe_disable_active"] = bool(
                    getattr(self, "_anti_forced_probe_disable_active", anti_runtime.get("forced_probe_disable_active", False))
                )
                anti_runtime["trigger_forced_probe_disable"] = int(
                    getattr(self, "_anti_trigger_forced_probe_disable", anti_runtime.get("trigger_forced_probe_disable", 0)) or 0
                )
            elif hasattr(self, "_anti_forced_probe_disable_active") or hasattr(self, "_anti_trigger_forced_probe_disable"):
                anti_runtime = {
                    "controls_enabled": True,
                    "throughput_degraded_active": False,
                    "structural_storm_active": False,
                    "forced_probe_disable_active": bool(getattr(self, "_anti_forced_probe_disable_active", False)),
                    "lane_cooldowns_active": 0,
                    "sector_cooldowns_active": 0,
                    "trigger_throughput_degraded": 0,
                    "trigger_structural_storm": 0,
                    "trigger_forced_probe_disable": int(getattr(self, "_anti_trigger_forced_probe_disable", 0) or 0),
                }
            self.anti_collapse_runtime = dict(anti_runtime or {})
            status_data["anti_collapse_runtime"] = dict(self.anti_collapse_runtime or {})
            trade_quality_runtime = dict(s_stats.get("trade_quality_runtime") or {})
            extra_trade_quality_runtime = dict(getattr(self, "_trade_quality_runtime", {}) or {})
            if extra_trade_quality_runtime:
                trade_quality_runtime.update(extra_trade_quality_runtime)
            self.trade_quality_runtime = dict(trade_quality_runtime or {})
            if self.trade_quality_runtime:
                status_data["trade_quality_runtime"] = dict(self.trade_quality_runtime)
            status_data["llm_wakeups_per_100_turns"] = (
                (float(status_data["llm_wakeups"]) * 100.0 / float(self.turns_used))
                if self.turns_used > 0
                else 0.0
            )

            # Update "last activity" memory after we've computed the final Activity value.
            # Do not record pause screens, since they are transient overlays.
            if (
                current_context != "pause"
                and activity
                and activity not in ("DISCONNECTED", "CONNECTING", "INITIALIZING")
            ):
                self._last_activity_context = activity

            # Always send credits, even if 0 (only skip if negative sentinel)
            status_data["credits"] = credits_out

            # Only include username/ship_level/ship_name if they have values
            # This preserves previously-known values in the manager
            if username:
                status_data["username"] = username
            if ship_level and ship_level not in ("0", "None", ""):
                status_data["ship_level"] = ship_level
            if ship_name and ship_name not in ("0", "None", ""):
                status_data["ship_name"] = ship_name

            await self._http_client.post(
                f"{self.manager_url}/bot/{self.bot_id}/status",
                json=status_data,
            )
        except Exception as e:
            logger.debug(f"Failed to report status: {e}")

    async def await_if_hijacked(self) -> None:
        """Block automation while the dashboard is hijacking this bot."""
        if not self._hijacked:
            return
        if self._hijack_step_tokens > 0:
            self._hijack_step_tokens -= 1
            return
        await self._hijack_event.wait()

    async def set_hijacked(self, enabled: bool) -> None:
        """Enable/disable hijack mode (pause automation only)."""
        if enabled == self._hijacked:
            return
        self._hijacked = enabled
        if enabled:
            # Clear any queued steps when entering hijack mode.
            self._hijack_step_tokens = 0

        if enabled:
            self._hijack_event.clear()
        else:
            self._hijack_event.set()

    async def request_step(self, checkpoints: int = 2) -> None:
        """Allow automation to pass a limited number of hijack checkpoints.

        This is designed to be used while hijacked. If not hijacked, it's a no-op.

        Args:
            checkpoints: Number of await_if_hijacked() calls to allow without blocking.
                         The default (2) permits one loop iteration to plan + act.
        """
        if not self._hijacked:
            return
        # Cap to avoid unbounded growth if a client misbehaves.
        self._hijack_step_tokens = min(self._hijack_step_tokens + max(0, int(checkpoints)), 100)

    def attach_screen_change_reporter(self, min_interval_s: float = 0.8) -> None:
        """Report status when the visible screen changes (throttled).

        This keeps `activity_context` in the swarm dashboard aligned with what the bot
        is actually seeing, without relying solely on periodic polling.
        """
        if self._screen_change_task is not None:
            return
        if not getattr(self, "session", None):
            return

        def _watch(snapshot: dict, raw: bytes) -> None:
            try:
                sh = snapshot.get("screen_hash") or ""
                if not sh:
                    return
                if sh == self._last_seen_screen_hash:
                    return
                self._last_seen_screen_hash = sh
                self._note_progress()
                self._screen_change_event.set()
            except Exception:
                return

        # Only report on real updates; raw may be empty in timeout reads.
        self.session.add_watch(_watch, interval_s=0.0)

        async def _loop() -> None:
            last_sent = 0.0
            while True:
                await self._screen_change_event.wait()
                self._screen_change_event.clear()
                now = time.monotonic()
                delay = (last_sent + float(min_interval_s)) - now
                if delay > 0:
                    await asyncio.sleep(delay)
                with contextlib.suppress(Exception):
                    await self.report_status()
                last_sent = time.monotonic()

        self._screen_change_task = asyncio.create_task(_loop())

    async def start_status_reporter(self, interval: float = 5.0) -> None:
        """Start background task to report status periodically."""
        self._reporting = True

        async def _report_loop():
            while self._reporting:
                await self.report_status()
                await asyncio.sleep(interval)

        self._report_task = asyncio.create_task(_report_loop())

    async def stop_status_reporter(self) -> None:
        """Stop the background status reporter."""
        self._reporting = False
        if hasattr(self, "_report_task"):
            self._report_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._report_task

    def log_action(
        self,
        action: str,
        sector: int,
        details: str | None = None,
        result: str = "pending",
        *,
        why: str | None = None,
        strategy_id: str | None = None,
        strategy_mode: str | None = None,
        strategy_intent: str | None = None,
        wake_reason: str | None = None,
        review_after_turns: int | None = None,
        decision_source: str | None = None,
        credits_before: int | None = None,
        credits_after: int | None = None,
        turns_before: int | None = None,
        turns_after: int | None = None,
        result_delta: int | None = None,
    ) -> None:
        """Log a bot action for the action feed."""
        import time

        action_entry = {
            "time": time.time(),
            "action": action,
            "sector": sector,
            "details": details,
            "result": result,
            "why": why,
            "strategy_id": strategy_id,
            "strategy_mode": strategy_mode,
            "strategy_intent": strategy_intent,
            "wake_reason": wake_reason,
            "review_after_turns": review_after_turns,
            "decision_source": decision_source,
            "credits_before": credits_before,
            "credits_after": credits_after,
            "turns_before": turns_before,
            "turns_after": turns_after,
            "result_delta": result_delta,
        }
        self.recent_actions.append(action_entry)
        action_key = str(action or "UNKNOWN").strip().upper() or "UNKNOWN"
        self.action_counters[action_key] = int(self.action_counters.get(action_key, 0) or 0) + 1
        intent_key = str(strategy_intent or "").strip().upper()
        if intent_key.startswith("RECOVERY:") or intent_key.startswith("BOOTSTRAP:"):
            self.recovery_actions = max(0, int(self.recovery_actions) + 1)
        # Keep only last 10 actions
        if len(self.recent_actions) > 10:
            self.recent_actions = self.recent_actions[-10:]

    async def report_error(
        self,
        error: Exception,
        exit_reason: str = "exception",
        *,
        fatal: bool = False,
        state: str | None = None,
    ) -> None:
        """Report detailed error information to manager.

        End-state: workers should be resilient and self-heal. Most exceptions are
        reported as `recovering` (not terminal) and the worker keeps running.
        """
        import time

        try:
            report_state = state
            if report_state is None:
                report_state = "error" if fatal else "recovering"
            # Ensure the next report_status() preserves this state.
            self.lifecycle_state = report_state
            await self._http_client.post(
                f"{self.manager_url}/bot/{self.bot_id}/status",
                json={
                    "state": report_state,
                    "error_message": str(error),
                    "error_type": type(error).__name__,
                    "error_timestamp": time.time(),
                    "exit_reason": exit_reason,
                    "last_action": self.current_action,
                    "recent_actions": self.recent_actions[-10:],
                },
            )
        except Exception as e:
            logger.debug(f"Failed to report error: {e}")

        # If this is a loop/orientation error, run diagnostics
        error_str = str(error).lower()
        if any(x in error_str for x in ["loop", "menu", "orientation", "stuck"]):
            try:
                import json
                from pathlib import Path

                from bbsbot.diagnostics.stuck_bot_analyzer import StuckBotAnalyzer
                from bbsbot.llm.config import LLMConfig, OllamaConfig
                from bbsbot.llm.manager import LLMManager

                llm_config = LLMConfig(
                    provider="ollama",
                    ollama=OllamaConfig(model="gemma3", timeout_seconds=30),
                )
                analyzer = StuckBotAnalyzer(LLMManager(llm_config))

                # Get loop history from loop detector
                loop_history = []
                if hasattr(self, "loop_detection") and hasattr(self.loop_detection, "alternation_history"):
                    loop_history = self.loop_detection.alternation_history

                diagnosis = await analyzer.analyze_stuck_bot(
                    bot_id=self.bot_id,
                    error_type=type(error).__name__,
                    recent_screens=self.diagnostic_buffer.get("recent_screens", []),
                    recent_prompts=self.diagnostic_buffer.get("recent_prompts", []),
                    loop_history=loop_history,
                    exit_reason=exit_reason,
                )

                # Log diagnostic results
                logger.info("llm_diagnosis", bot_id=self.bot_id, diagnosis=diagnosis)

                # Save to diagnostic log file
                diagnostic_file = Path(f"logs/diagnostics/{self.bot_id}_diagnosis.json")
                diagnostic_file.parent.mkdir(parents=True, exist_ok=True)
                with diagnostic_file.open("w") as f:
                    json.dump(
                        {
                            "timestamp": time.time(),
                            "bot_id": self.bot_id,
                            "error": str(error),
                            "diagnosis": diagnosis,
                        },
                        f,
                        indent=2,
                    )

                print(f"  🔍 LLM Diagnosis saved to: {diagnostic_file}")

            except Exception as diag_error:
                logger.warning(f"Diagnostic analysis failed: {diag_error}")

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.stop_status_reporter()
        await self.set_hijacked(False)
        if self._screen_change_task is not None:
            self._screen_change_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._screen_change_task
            self._screen_change_task = None
        await self._http_client.aclose()


async def _run_worker(config: str, bot_id: str, manager_url: str) -> None:
    """Run worker bot async.

    Args:
        config: Path to bot config YAML
        bot_id: Unique bot ID
        manager_url: URL of swarm manager
    """
    from bbsbot.games.tw2002.character import CharacterState

    config_path = Path(config)
    logger.info(f"Loading config: {config_path}")

    import yaml

    with config_path.open() as f:
        config_dict = yaml.safe_load(f)

    config_obj = BotConfig(**config_dict)

    worker = WorkerBot(bot_id, config_obj, manager_url)
    term_bridge = None

    # Resolve credentials from config + persistent stores; retries may refresh identity.
    identity_store = BotIdentityStore()
    account_pool = AccountPoolStore()
    username = ""
    character_password = ""
    game_password = ""
    identity_source = "unknown"
    refresh_identity = True

    def _resolve_identity() -> None:
        nonlocal username, character_password, game_password, identity_source
        username, character_password, game_password, identity_source = _resolve_worker_identity(
            bot_id=bot_id,
            config_dict=config_dict,
            config_obj=config_obj,
            identity_store=identity_store,
            account_pool=account_pool,
            config_path=config_path,
        )
        with contextlib.suppress(Exception):
            # Make status reflect the actual character name promptly.
            worker.character_name = username

    _resolve_identity()
    refresh_identity = False

    # Register with manager (best-effort; don't crash the worker if manager is down).
    with contextlib.suppress(Exception):
        await worker.register_with_manager()

    # Start reporting immediately so the manager doesn't mark "no heartbeat".
    await worker.report_status()
    await worker.start_status_reporter(interval=5.0)

    # Optional: connect terminal bridge (best-effort).
    try:
        from bbsbot.swarm.term_bridge import TermBridge

        term_bridge = TermBridge(worker, bot_id=bot_id, manager_url=manager_url)
        term_bridge.attach_session()
        await term_bridge.start()
    except Exception as e:
        logger.warning(f"Terminal bridge disabled: {e}")

    # Resilience loop: never exit on recoverable errors.
    backoff_s = 1.0
    failures = 0

    class _RecoveryBudget:
        def __init__(self, *, window_s: float = 600.0) -> None:
            self.window_s = float(window_s)
            self._events: dict[str, deque[float]] = {
                "auth": deque(),
                "game_full": deque(),
                "network": deque(),
                "logic": deque(),
                "watchdog": deque(),
            }
            self._limits: dict[str, int] = {
                "auth": 1,  # unrecoverable; block immediately
                "game_full": 1,  # stop retrying character creation when game is full
                "network": 5,  # 5 in 10m => blocked
                "logic": 5,  # 5 in 10m => blocked
                "watchdog": 3,  # 3 in 10m => blocked
            }

        def note(self, cls: str) -> int:
            now = time.monotonic()
            dq = self._events.setdefault(cls, deque())
            dq.append(now)
            cutoff = now - self.window_s
            while dq and dq[0] < cutoff:
                dq.popleft()
            return len(dq)

        def exceeded(self, cls: str) -> bool:
            limit = int(self._limits.get(cls, 5))
            dq = self._events.get(cls) or deque()
            return len(dq) >= limit

        def reset(self) -> None:
            for dq in self._events.values():
                dq.clear()

    def _classify_exception(e: Exception) -> str:
        msg = str(e).lower()
        et = type(e).__name__.lower()
        if "gamefullerror" in et or "game is full" in msg or "new player not allowed - game full" in msg:
            return "game_full"
        if "watchdog_stuck" in msg or "watchdog" in msg:
            return "watchdog"
        if (
            "invalid_password" in msg
            or "auth_failed" in msg
            or "prompt.character_password" in msg
            or "prompt.game_password" in msg
            or "prompt.private_game_password" in msg
        ):
            return "auth"
        if "connection" in msg or "not connected" in msg or "timeout" in msg:
            return "network"
        if "connectionerror" in et or "timeout" in et:
            return "network"
        return "logic"

    budget = _RecoveryBudget(window_s=600.0)
    blocked_level: dict[str, int] = {"auth": 0, "network": 0, "logic": 0, "watchdog": 0}
    blocked_schedule_s = [300.0, 900.0, 1800.0]  # 5m, 15m, 30m
    rng = __import__("random").Random(1)
    active_session_id: str | None = None

    def _metrics_snapshot() -> dict[str, int | None]:
        credits_val: int | None = None
        try:
            if worker.game_state and worker.game_state.credits is not None:
                credits_val = int(worker.game_state.credits)
            elif getattr(worker, "current_credits", None) is not None:
                credits_val = int(worker.current_credits)
        except Exception:
            credits_val = None
        sector_val: int | None = None
        try:
            if worker.current_sector and int(worker.current_sector) > 0:
                sector_val = int(worker.current_sector)
            elif worker.game_state and getattr(worker.game_state, "sector", None):
                sector_val = int(worker.game_state.sector)
        except Exception:
            sector_val = None
        return {
            "credits": credits_val,
            "turns_executed": int(getattr(worker, "turns_used", 0) or 0),
            "trades_executed": int(getattr(worker, "trades_executed", 0) or 0),
            "sector": sector_val,
        }

    def _end_active_session(
        *,
        stop_reason: str,
        state: str | None = None,
        exit_reason: str | None = None,
        error: Exception | None = None,
    ) -> None:
        nonlocal active_session_id
        if not active_session_id:
            return
        metrics = _metrics_snapshot()
        error_type = type(error).__name__ if error is not None else None
        error_message = str(error) if error is not None else None
        identity_store.end_session(
            bot_id=bot_id,
            session_id=active_session_id,
            stop_reason=stop_reason,
            state=state,
            exit_reason=exit_reason,
            error_type=error_type,
            error_message=error_message,
            turns_executed=metrics["turns_executed"],
            credits=metrics["credits"],
            trades_executed=metrics["trades_executed"],
            sector=metrics["sector"],
        )
        active_session_id = None

    try:
        while True:
            if refresh_identity:
                _resolve_identity()
                refresh_identity = False

            active_session = identity_store.start_session(bot_id=bot_id, state="starting")
            active_session_id = active_session.id
            # Preserve run counters across reconnect cycles in the same worker process.
            # Reset only once at process start.
            if not bool(getattr(worker, "_metrics_initialized", False)):
                worker.reset_runtime_session_metrics()
                worker._metrics_initialized = True
            try:
                # Ensure watchdog is running once per process.
                worker.start_watchdog(stuck_timeout_s=120.0, check_interval_s=5.0)

                # (Re)connect if needed.
                if not getattr(worker, "session", None) or not worker.session.is_connected():
                    with contextlib.suppress(Exception):
                        await worker.disconnect()
                    logger.info(f"Connecting to {config_obj.connection.host}:{config_obj.connection.port}")
                    worker.ai_activity = "CONNECTING"
                    worker.lifecycle_state = "recovering"
                    await worker.connect(
                        host=config_obj.connection.host,
                        port=config_obj.connection.port,
                    )
                    # Push status updates on screen changes (throttled) once session exists.
                    worker.attach_screen_change_reporter(min_interval_s=0.8)

                # Login (idempotent-ish; may early-return if already in game).
                worker.ai_activity = "LOGGING_IN"
                worker.lifecycle_state = "recovering"
                await worker.login_sequence(
                    game_password=game_password,
                    character_password=character_password,
                    username=username,
                )

                # Initialize knowledge and strategy (safe to re-init across reconnects).
                game_letter = config_obj.connection.game_letter or worker.last_game_letter
                worker.init_knowledge(config_obj.connection.host, config_obj.connection.port, game_letter)
                worker.init_strategy()
                worker.lifecycle_state = "running"
                await worker.report_status()

                # Run trading loop; end-state: loop returns only on internal soft-stops,
                # and we immediately restart rather than exiting the worker.
                from bbsbot.games.tw2002.character import CharacterState
                from bbsbot.games.tw2002.cli_impl import run_trading_loop

                char_state = CharacterState(name=bot_id)
                worker.ai_activity = "RUNNING"
                worker.lifecycle_state = "running"
                await run_trading_loop(worker, config_obj, char_state)
                _end_active_session(
                    stop_reason="soft_stop",
                    state="running",
                    exit_reason="soft_stop",
                )

                # If the trading loop returns, treat it as a soft-stop and restart.
                worker.ai_activity = "RESTARTING (soft-stop)"
                await worker.report_status()
                await asyncio.sleep(2.0)

                # Reset backoff after any successful run segment.
                backoff_s = 1.0
                failures = 0
                budget.reset()
                for k in blocked_level:
                    blocked_level[k] = 0

            except asyncio.CancelledError:
                _end_active_session(stop_reason="cancelled", state="stopped", exit_reason="cancelled")
                raise
            except Exception as e:
                failures += 1
                logger.error(f"Worker cycle error: {e}", exc_info=True)
                cls = _classify_exception(e)
                budget.note(cls)
                if cls == "auth":
                    with contextlib.suppress(Exception):
                        account_pool.release_by_bot(bot_id=bot_id, cooldown_s=1800)
                    refresh_identity = True
                _end_active_session(
                    stop_reason=f"error:{cls}",
                    state="recovering",
                    exit_reason="recovering",
                    error=e,
                )

                # Escalation: stop thrashing; enter blocked with long backoff.
                if cls in ("auth", "game_full") or budget.exceeded(cls):
                    lvl = int(blocked_level.get(cls, 0))
                    blocked_level[cls] = min(lvl + 1, len(blocked_schedule_s) - 1)
                    base_sleep = (
                        86400.0 if cls == "game_full" else blocked_schedule_s[min(lvl, len(blocked_schedule_s) - 1)]
                    )
                    # Add small deterministic jitter to avoid a herd on the minute.
                    sleep_s = float(base_sleep) * (0.85 + 0.3 * rng.random())
                    if cls == "game_full":
                        worker.ai_activity = "BLOCKED GAME_FULL"
                    else:
                        worker.ai_activity = f"BLOCKED {int(sleep_s // 60)}m ({cls})"
                    worker.lifecycle_state = "blocked"
                    await worker.report_error(
                        e,
                        exit_reason=f"blocked_{cls}",
                        fatal=False,
                        state="blocked",
                    )
                    with contextlib.suppress(Exception):
                        await worker.report_status()
                    await asyncio.sleep(sleep_s)
                    # After blocked sleep, keep the process alive and try again.
                    backoff_s = 1.0
                    continue

                # Report as recovering (non-terminal).
                worker.lifecycle_state = "recovering"
                await worker.report_error(e, exit_reason="recovering", fatal=False, state="recovering")

                # Try in-session recovery first (escape menus, get back to safe prompt).
                recovered = False
                try:
                    worker.ai_activity = f"RECOVERING ({type(e).__name__})"
                    await worker.report_status()
                    await worker.recover(max_attempts=20)
                    recovered = True
                except Exception:
                    recovered = False

                # If recovery didn't help, force reconnect.
                if not recovered:
                    with contextlib.suppress(Exception):
                        await worker.disconnect()

                # Exponential backoff to avoid thrashing the server on persistent failures.
                sleep_s = min(60.0, backoff_s)
                worker.ai_activity = f"BACKOFF {sleep_s:.0f}s (failures={failures})"
                worker.lifecycle_state = "recovering"
                with contextlib.suppress(Exception):
                    await worker.report_status()
                await asyncio.sleep(sleep_s)
                backoff_s = min(60.0, backoff_s * 2.0)
                continue
    finally:
        _end_active_session(stop_reason="shutdown", state="stopped", exit_reason="shutdown")
        with contextlib.suppress(Exception):
            account_pool.release_by_bot(bot_id=bot_id, cooldown_s=0)
        with contextlib.suppress(Exception):
            await worker.stop_status_reporter()
        with contextlib.suppress(Exception):
            await worker.disconnect()
        if term_bridge is not None:
            with contextlib.suppress(Exception):
                await term_bridge.stop()
        await worker.cleanup()


@click.command()
@click.option(
    "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to bot config file",
)
@click.option(
    "--bot-id",
    required=True,
    help="Unique bot identifier",
)
@click.option(
    "--manager-url",
    default=MANAGER_URL_DEFAULT,
    help="Swarm manager URL",
)
def main(config: str, bot_id: str, manager_url: str) -> None:
    """Run a bot worker process."""
    try:
        asyncio.run(_run_worker(config, bot_id, manager_url))
    except Exception as e:
        logger.error(f"Bot worker fatal: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
