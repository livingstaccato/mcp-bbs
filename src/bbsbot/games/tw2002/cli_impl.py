# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Implementation helpers for the TW2002 CLI."""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
import time
from collections import deque
from typing import TYPE_CHECKING

from bbsbot.games.tw2002.anti_collapse import controls_to_runtime_map, resolve_anti_collapse_controls
from bbsbot.games.tw2002.orientation import OrientationError
from bbsbot.games.tw2002.strategies.base import TradeAction, TradeResult
from bbsbot.games.tw2002.visualization import GoalStatusDisplay
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import BotConfig

logger = get_logger(__name__)

# Commodity name patterns for matching in "How many holds of X" prompts
_COMMODITY_PATTERNS = {
    "fuel_ore": re.compile(r"fuel\s*ore", re.IGNORECASE),
    "organics": re.compile(r"organics", re.IGNORECASE),
    "equipment": re.compile(r"equipment", re.IGNORECASE),
}


def _is_port_qty_prompt(line: str) -> bool:
    """True if `line` is the active port quantity prompt line.

    The screen buffer often contains old "How many ..." lines above the current
    prompt (e.g. while haggling). We must only treat the *active prompt line* as
    the quantity prompt, otherwise we keep re-sending qty while in haggle.
    """
    ll = (line or "").strip().lower()
    if not ll:
        return False
    if "how many" not in ll:
        return False
    return bool(re.search(r"(?i)\bhow\s+many\b.*\[[\d,]+\]\s*\?\s*$", ll))


def _extract_port_qty_cap(
    prompt_line: str,
    screen_text: str | None = None,
    *,
    is_sell: bool | None = None,
) -> int | None:
    """Extract a safe max qty from the active quantity prompt/screen.

    We prefer prompt-confirmed limits over stale strategy/state values.
    For sell prompts, if the screen explicitly says "You have X in your holds",
    clamp to that value.
    """
    ll = (prompt_line or "").strip().lower()
    if not ll:
        return None

    cap: int | None = None
    m_default = re.search(r"\[([\d,]+)\]", ll)
    if m_default:
        with contextlib.suppress(Exception):
            cap = max(0, int(m_default.group(1).replace(",", "")))

    if is_sell is None:
        is_sell = " sell" in ll

    if is_sell and screen_text:
        m_have = re.search(r"\byou have\s+([\d,]+)\s+in your holds\b", screen_text.lower())
        if m_have:
            with contextlib.suppress(Exception):
                have = max(0, int(m_have.group(1).replace(",", "")))
                cap = have if cap is None else min(cap, have)

    return cap


def _get_cargo_ledger(bot) -> dict[str, int]:
    """Get or initialize deterministic cargo ledger on the bot."""
    ledger = getattr(bot, "_cargo_ledger", None)
    if not isinstance(ledger, dict):
        ledger = {"fuel_ore": 0, "organics": 0, "equipment": 0}
        bot._cargo_ledger = ledger
    for key in ("fuel_ore", "organics", "equipment"):
        try:
            ledger[key] = max(0, int(ledger.get(key, 0) or 0))
        except Exception:
            ledger[key] = 0
    return ledger


def _apply_cargo_ledger_to_state(bot, state) -> None:
    """Project deterministic ledger values into state/semantic structures."""
    ledger = _get_cargo_ledger(bot)
    with contextlib.suppress(Exception):
        state.cargo_fuel_ore = int(ledger.get("fuel_ore", 0))
    with contextlib.suppress(Exception):
        state.cargo_organics = int(ledger.get("organics", 0))
    with contextlib.suppress(Exception):
        state.cargo_equipment = int(ledger.get("equipment", 0))
    with contextlib.suppress(Exception):
        if getattr(bot, "game_state", None) is not None:
            bot.game_state.cargo_fuel_ore = int(ledger.get("fuel_ore", 0))
            bot.game_state.cargo_organics = int(ledger.get("organics", 0))
            bot.game_state.cargo_equipment = int(ledger.get("equipment", 0))
    with contextlib.suppress(Exception):
        sem = getattr(bot, "last_semantic_data", None)
        if isinstance(sem, dict):
            sem["cargo_fuel_ore"] = int(ledger.get("fuel_ore", 0))
            sem["cargo_organics"] = int(ledger.get("organics", 0))
            sem["cargo_equipment"] = int(ledger.get("equipment", 0))


def _record_cargo_ledger_trade(bot, commodity: str | None, is_buy: bool | None, qty: int | None) -> None:
    """Apply a completed trade qty to deterministic cargo ledger."""
    if not commodity or is_buy is None:
        return
    if commodity not in {"fuel_ore", "organics", "equipment"}:
        return
    try:
        qty_val = max(0, int(qty or 0))
    except Exception:
        qty_val = 0
    if qty_val <= 0:
        return
    ledger = _get_cargo_ledger(bot)
    current = max(0, int(ledger.get(commodity, 0) or 0))
    ledger[commodity] = current + qty_val if is_buy else max(0, current - qty_val)
    with contextlib.suppress(Exception):
        if getattr(bot, "game_state", None) is not None:
            bot.game_state.cargo_fuel_ore = int(ledger.get("fuel_ore", 0))
            bot.game_state.cargo_organics = int(ledger.get("organics", 0))
            bot.game_state.cargo_equipment = int(ledger.get("equipment", 0))
    with contextlib.suppress(Exception):
        sem = getattr(bot, "last_semantic_data", None)
        if isinstance(sem, dict):
            sem["cargo_fuel_ore"] = int(ledger.get("fuel_ore", 0))
            sem["cargo_organics"] = int(ledger.get("organics", 0))
            sem["cargo_equipment"] = int(ledger.get("equipment", 0))


def _record_cargo_value_hint(bot, commodity: str | None, unit_price: int | None, *, side: str | None = None) -> None:
    """Record a conservative per-unit liquidation hint for cargo valuation fallback.

    `side` comes from the port quote text:
    - "buy": port buys from us (realized sell price)
    - "sell": port sells to us (our buy cost)
    """
    if commodity not in {"fuel_ore", "organics", "equipment"}:
        return
    try:
        unit = int(unit_price or 0)
    except Exception:
        unit = 0
    if unit <= 0:
        return

    side_norm = str(side or "").strip().lower()
    # If this was a buy from port, use a haircut so fallback net-worth doesn't
    # overstate liquidation value.
    candidate = unit if side_norm == "buy" else max(1, int(round(unit * 0.75)))

    hints = getattr(bot, "_cargo_value_hints", None)
    if not isinstance(hints, dict):
        hints = {}
        bot._cargo_value_hints = hints

    prev = int(hints.get(commodity, 0) or 0)
    if prev <= 0:
        hints[commodity] = candidate
        return
    # Smooth updates to reduce volatility from one noisy quote.
    hints[commodity] = max(1, int(round((prev * 3 + candidate) / 4)))


def _create_strategy_instance(strategy_name: str, config: BotConfig, knowledge):
    """Create a strategy instance by name (fallback to opportunistic)."""
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
    from bbsbot.games.tw2002.strategies.opportunistic import OpportunisticStrategy
    from bbsbot.games.tw2002.strategies.profitable_pairs import ProfitablePairsStrategy
    from bbsbot.games.tw2002.strategies.twerk_optimized import TwerkOptimizedStrategy

    mapping = {
        "ai_strategy": AIStrategy,
        "opportunistic": OpportunisticStrategy,
        "profitable_pairs": ProfitablePairsStrategy,
        "twerk_optimized": TwerkOptimizedStrategy,
    }
    cls = mapping.get(strategy_name, OpportunisticStrategy)
    return cls(config, knowledge)


def _normalize_port_side(value: str | None) -> str | None:
    if not value:
        return None
    side = str(value).strip().lower()
    if side in {"buying", "buy"}:
        return "buying"
    if side in {"selling", "sell"}:
        return "selling"
    return None


def _derive_port_statuses(port_class: str | None, info) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if info is not None:
        raw = getattr(info, "port_status", None) or {}
        for commodity, side in raw.items():
            norm = _normalize_port_side(side)
            if norm and commodity in {"fuel_ore", "organics", "equipment"}:
                statuses[commodity] = norm

    if statuses:
        return statuses

    if not port_class or len(port_class) != 3:
        return statuses

    cls = str(port_class).upper()
    return {
        "fuel_ore": "buying" if cls[0] == "B" else "selling",
        "organics": "buying" if cls[1] == "B" else "selling",
        "equipment": "buying" if cls[2] == "B" else "selling",
    }


def _choose_no_trade_guard_action(
    state,
    knowledge,
    credits_now: int,
    *,
    allow_buy: bool = True,
    guard_overage: int = 0,
    previous_sector: int | None = None,
    recent_sectors: list[int] | deque[int] | None = None,
) -> tuple[TradeAction, dict] | None:
    """Hard trade-urgency override when the no-trade guard is active."""
    if state.context != "sector_command":
        return None

    current_sector = int(state.sector or 0)
    info = knowledge.get_sector_info(current_sector) if current_sector > 0 else None
    has_port_now = bool(getattr(state, "has_port", False))
    has_port_known_here = bool(getattr(info, "has_port", False))
    local_port_available = current_sector > 0 and (has_port_now or has_port_known_here)
    statuses = _derive_port_statuses(getattr(state, "port_class", None) or getattr(info, "port_class", None), info)
    cargo = {
        "fuel_ore": int(getattr(state, "cargo_fuel_ore", 0) or 0),
        "organics": int(getattr(state, "cargo_organics", 0) or 0),
        "equipment": int(getattr(state, "cargo_equipment", 0) or 0),
    }
    cargo_total = sum(max(0, int(v or 0)) for v in cargo.values())
    primary_cargo = max(cargo.items(), key=lambda kv: int(kv[1] or 0))[0] if cargo_total > 0 else None
    tiny_cargo_stall = bool(cargo_total > 0 and cargo_total <= 3 and int(guard_overage or 0) >= 12)
    units = (getattr(info, "port_trading_units", {}) or {}) if info else {}
    holds_free = 0
    with contextlib.suppress(Exception):
        if getattr(state, "holds_free", None) is not None:
            holds_free = max(0, int(getattr(state, "holds_free", 0) or 0))
        else:
            holds_total = getattr(state, "holds_total", None)
            if holds_total is not None:
                holds_free = max(0, int(holds_total) - int(cargo_total))
            else:
                # Orientation can miss quick-stats rows transiently; keep a safe
                # fallback so no-trade guard can still bootstrap local buys.
                holds_free = max(1, 20 - int(cargo_total)) if int(cargo_total) > 0 else 6

    if local_port_available:
        # First priority: sell whatever we already hold into local demand.
        for commodity, qty in cargo.items():
            if qty <= 0 or statuses.get(commodity) != "buying":
                continue
            demand_units = units.get(commodity)
            if demand_units is not None:
                with contextlib.suppress(Exception):
                    if int(demand_units) <= 0:
                        continue
            if qty > 0:
                return TradeAction.TRADE, {
                    "commodity": commodity,
                    "action": "sell",
                    "max_quantity": qty,
                    "urgency": "no_trade_guard",
                }

        # If we have cargo and status hints are missing, probe one sell commodity.
        # Dock failure/non-port is handled by execute_port_trade() and cached.
        if not statuses:
            for commodity, qty in cargo.items():
                if qty > 0:
                    return TradeAction.TRADE, {
                        "commodity": commodity,
                        "action": "sell",
                        "max_quantity": qty,
                        "urgency": "no_trade_guard",
                    }

        # If local port doesn't buy what we carry, route to a better sell target.
        if cargo_total > 0:
            reroute = _choose_guard_reroute_action(
                state=state,
                knowledge=knowledge,
                previous_sector=previous_sector,
                recent_sectors=list(recent_sectors or []),
                commodity=primary_cargo,
                trade_action="sell",
            )
            # Tiny stale cargo can trap bots in endless sell reroutes.
            # Once overage is high, allow guarded buy bootstrap to resume instead.
            if reroute is not None and not tiny_cargo_stall:
                return reroute

        # Second priority: buy the cheapest local commodity the port is selling.
        # Bootstrap mode can disable forced buys to avoid draining bankroll
        # before we have stable sell paths.
        if allow_buy and holds_free > 0 and int(credits_now or 0) > 0:
            sellables: list[str] = []
            for commodity in ("fuel_ore", "organics", "equipment"):
                if statuses.get(commodity) != "selling":
                    continue
                supply_units = units.get(commodity)
                if supply_units is not None:
                    with contextlib.suppress(Exception):
                        if int(supply_units) <= 0:
                            continue
                sellables.append(commodity)
            if not sellables:
                # If units are unknown, keep a fallback to avoid deadlock.
                sellables = [c for c in ("fuel_ore", "organics", "equipment") if statuses.get(c) == "selling"]
            # Only force local buys when we already know a nearby buyer path.
            # This avoids filling holds with dead-end cargo and burning turns.
            current_sector_for_buy = int(current_sector or 0)
            buyer_paths: dict[str, list[int]] = {}
            if current_sector_for_buy > 0:
                for comm in list(sellables):
                    path = _find_nearest_market_path(
                        state=state,
                        knowledge=knowledge,
                        commodity=comm,
                        desired_side="buying",
                        max_hops=8,
                    )
                    if path:
                        buyer_paths[comm] = path
            if buyer_paths:
                sellables = [c for c in sellables if c in buyer_paths]
            elif guard_overage < 8:
                sellables = []
            if sellables:
                prices = (getattr(info, "port_prices", {}) or {}) if info else {}
                commodity_priority = {"fuel_ore": 0, "organics": 1, "equipment": 2}

                def _rank_buy(comm: str) -> tuple[int, str]:
                    quoted = (prices.get(comm) or {}).get("sell")
                    try:
                        # Unknown quote: prioritize traditionally cheaper holds.
                        p = int(quoted) if quoted is not None else (10**9) + int(commodity_priority.get(comm, 99))
                    except Exception:
                        p = (10**9) + int(commodity_priority.get(comm, 99))
                    return (p, comm)

                commodity = sorted(sellables, key=_rank_buy)[0]
                quoted = (prices.get(commodity) or {}).get("sell")
                qty = 1
                credits_val = max(0, int(credits_now or 0))
                try:
                    qv = int(quoted) if quoted is not None else 0
                except Exception:
                    qv = 0
                if qv > 0:
                    # Preserve a bankroll reserve, but relax as stale pressure
                    # grows so low-credit bots can still execute recovery buys.
                    if guard_overage >= 16:
                        reserve_floor = max(20, int(credits_val * 0.08))
                    elif guard_overage >= 8:
                        reserve_floor = max(30, int(credits_val * 0.12))
                    else:
                        reserve_floor = max(40, int(credits_val * 0.18))
                    spend_cap = max(0, credits_val - reserve_floor)
                    affordable = int(spend_cap // qv)
                    if affordable <= 0 and guard_overage >= 16:
                        emergency_floor = max(10, int(credits_val * 0.03))
                        if credits_val >= (qv + emergency_floor):
                            affordable = 1
                    # If we cannot afford even one unit, do not force a local buy
                    # and fall back to movement/exploration below.
                    # Buy more than one unit when possible so guard-mode bots
                    # can recover CPT instead of getting stuck in 1-unit churn.
                    if affordable > 0:
                        if guard_overage >= 20:
                            buy_cap = min(holds_free, 12)
                        elif guard_overage >= 8:
                            buy_cap = min(holds_free, 8)
                        else:
                            buy_cap = min(holds_free, 4)
                        qty = min(buy_cap, affordable)
                    else:
                        qty = 0
                else:
                    # Unknown price: only probe if bankroll can support a
                    # conservative minimum per-commodity estimate.
                    # Below 500 credits, avoid blind organics/equipment probes.
                    if credits_val < 500 and commodity != "fuel_ore":
                        qty = 0
                    else:
                        min_probe_credit = {
                            "fuel_ore": 35,
                            "organics": 45,
                            "equipment": 80,
                        }.get(commodity, 40)
                        if credits_val < int(min_probe_credit):
                            qty = 0
                        elif credits_val < 300:
                            qty = min(holds_free, 1)
                        else:
                            qty = min(holds_free, 4 if guard_overage >= 20 else 2)
                if qty > 0:
                    return TradeAction.TRADE, {
                        "commodity": commodity,
                        "action": "buy",
                        "max_quantity": qty,
                        "urgency": "no_trade_guard",
                    }
            else:
                # Move to a known nearby seller before forcing speculative buys.
                reroute_buy = _choose_guard_reroute_action(
                    state=state,
                    knowledge=knowledge,
                    previous_sector=previous_sector,
                    recent_sectors=list(recent_sectors or []),
                    commodity="fuel_ore",
                    trade_action="buy",
                )
                if reroute_buy is not None:
                    return reroute_buy
        # If guard has been active for a while and we still cannot construct a
        # local buy/sell, perform a minimal trade probe. This forces a dock
        # attempt which updates no-port knowledge on failure and breaks stale
        # move-only loops.
        if guard_overage >= 4:
            credits_val = max(0, int(credits_now or 0))
            if cargo_total > 0 and not tiny_cargo_stall:
                probe_commodity = str(primary_cargo or "fuel_ore")
                reroute = _choose_guard_reroute_action(
                    state=state,
                    knowledge=knowledge,
                    previous_sector=previous_sector,
                    recent_sectors=list(recent_sectors or []),
                    commodity=probe_commodity,
                    trade_action="sell",
                )
                if reroute is not None:
                    return reroute
                # If local market status is known and this port is not buying the
                # commodity we hold, skip futile local sell probes.
                if statuses and str(statuses.get(probe_commodity, "")).lower() != "buying":
                    probe_commodity = ""
                if probe_commodity:
                    return TradeAction.TRADE, {
                        "commodity": probe_commodity,
                        "action": "sell",
                        "max_quantity": 1,
                        "urgency": "no_trade_probe",
                    }

            # With empty holds, "sell probes" are pure waste and can loop forever.
            # In bootstrap/allow_buy=False mode, permit a guarded 1-unit buy only
            # after persistent stall; otherwise fall back to movement/exploration.
            sellables = [c for c in ("fuel_ore", "organics", "equipment") if statuses.get(c) == "selling"]
            can_probe_buy = (
                bool(sellables)
                and holds_free > 0
                and (
                    (allow_buy and credits_val >= 120)
                    or ((not allow_buy) and guard_overage >= 10 and credits_val >= 260)
                )
            )
            if can_probe_buy:
                prices = (getattr(info, "port_prices", {}) or {}) if info else {}

                def _probe_rank(comm: str) -> tuple[int, str]:
                    quoted = (prices.get(comm) or {}).get("sell")
                    try:
                        return (int(quoted), comm) if quoted is not None else (10**9, comm)
                    except Exception:
                        return (10**9, comm)

                probe_commodity = sorted(sellables, key=_probe_rank)[0]
                return TradeAction.TRADE, {
                    "commodity": probe_commodity,
                    "action": "buy",
                    "max_quantity": 1,
                    "urgency": "no_trade_probe",
                }
            # No safe probe available here; fall through to movement/explore.

    # Severe stale/no-trade recovery: when we have no confirmed local port intel,
    # actively probe for one instead of explore-only wandering.
    if not local_port_available and guard_overage >= 12:
        credits_val = max(0, int(credits_now or 0))
        if cargo_total > 0:
            probe_sell = str(primary_cargo or "fuel_ore")
            return TradeAction.TRADE, {
                "commodity": probe_sell,
                "action": "sell",
                "max_quantity": 1,
                "urgency": "no_trade_probe",
            }
        if holds_free > 0 and credits_val >= 120:
            probe_order = ["fuel_ore", "organics", "equipment"]
            probe_index = abs(int(current_sector) + int(guard_overage)) % len(probe_order)
            probe_commodity = probe_order[probe_index]
            return TradeAction.TRADE, {
                "commodity": probe_commodity,
                "action": "buy",
                "max_quantity": 1,
                "urgency": "no_trade_probe",
            }

    # Not at a usable port: force movement to nearest known port.
    if current_sector > 0:
        reroute = _choose_guard_reroute_action(
            state=state,
            knowledge=knowledge,
            previous_sector=previous_sector,
            recent_sectors=list(recent_sectors or []),
            commodity=primary_cargo,
            trade_action="sell" if cargo_total > 0 else None,
        )
        if reroute is not None:
            action, params = reroute
            if action == TradeAction.MOVE:
                params = dict(params)
                params.setdefault("urgency", "no_trade_guard")
                return action, params

    warps = [int(w) for w in (state.warps or []) if int(w) != current_sector]
    known_non_port = set()
    for warp in warps:
        with contextlib.suppress(Exception):
            info = knowledge.get_sector_info(int(warp))
            if info is not None and getattr(info, "has_port", None) is False:
                known_non_port.add(int(warp))
    preferred_warps = [w for w in warps if int(w) not in known_non_port]
    # Hard stall escape: if guard has been over threshold for a long time and we
    # still cannot resolve a trade/reroute, force a long-jump move. Non-adjacent
    # sector moves are handled by warp_to_sector() via autopilot and help break
    # deterministic ABAB local loops.
    if guard_overage >= 6 and current_sector > 0:
        jump_target = _choose_guard_escape_jump_target(
            current_sector=current_sector,
            recent_sectors=list(recent_sectors or []),
        )
        if jump_target and jump_target != current_sector:
            return TradeAction.MOVE, {
                "target_sector": int(jump_target),
                "path": [int(current_sector), int(jump_target)],
                "urgency": "no_trade_escape_jump",
            }
    if preferred_warps:
        target = (
            sorted(w for w in preferred_warps if int(w) != int(previous_sector or 0))
            or sorted(preferred_warps)
        )
        chosen = int(target[0])
        return TradeAction.EXPLORE, {"direction": chosen, "urgency": "no_trade_guard"}
    if warps:
        target = sorted(w for w in warps if int(w) != int(previous_sector or 0)) or sorted(warps)
        chosen = int(target[0])
        return TradeAction.EXPLORE, {"direction": chosen, "urgency": "no_trade_guard"}
    return None


def _choose_guard_reroute_action(
    *,
    state,
    knowledge,
    previous_sector: int | None = None,
    recent_sectors: list[int] | deque[int] | None = None,
    commodity: str | None = None,
    trade_action: str | None = None,
) -> tuple[TradeAction, dict] | None:
    """Move away from a local no-trade loop to a different known port."""
    current_sector = int(getattr(state, "sector", 0) or 0)
    if current_sector <= 0:
        return None

    target_commodity = str(commodity or "").strip().lower()
    if target_commodity not in {"fuel_ore", "organics", "equipment"}:
        target_commodity = ""
    desired_side = None
    action_side = str(trade_action or "").strip().lower()
    if target_commodity and action_side == "sell":
        desired_side = "buying"
    elif target_commodity and action_side == "buy":
        desired_side = "selling"

    recent_tail = list(recent_sectors or [])
    recent_avoid = {int(s) for s in recent_tail[-8:] if int(s) != current_sector}

    best_pref: tuple[tuple[int, int, int, int, int], list[int]] | None = None
    best_any: tuple[tuple[int, int, int, int], list[int]] | None = None
    best_conflict: tuple[tuple[int, int, int, int], list[int]] | None = None
    for sector, info in (getattr(knowledge, "_sectors", {}) or {}).items():
        try:
            target_sector = int(sector)
        except Exception:
            continue
        if target_sector <= 0 or target_sector == current_sector:
            continue
        if previous_sector is not None and target_sector == int(previous_sector):
            continue
        if not getattr(info, "has_port", False):
            continue
        statuses = _derive_port_statuses(getattr(info, "port_class", None), info)
        side = statuses.get(target_commodity) if target_commodity else None
        path = knowledge.find_path(current_sector, target_sector, max_hops=20)
        # Guard mode can safely use non-adjacent direct jump requests; the game
        # autopilot resolves full routes server-side even when local map knowledge
        # is sparse. Keep these candidates, but score them as more expensive than
        # known-map paths.
        if not path or len(path) < 2:
            path = [current_sector, target_sector]
            hops = 25
        else:
            hops = len(path) - 1
        recent_penalty = 1 if target_sector in recent_avoid else 0
        quality = 0
        with contextlib.suppress(Exception):
            quality += 1 if getattr(info, "port_status", None) else 0
            quality += 1 if getattr(info, "port_prices", None) else 0

        any_key = (recent_penalty, hops, -quality, target_sector)
        if desired_side and side and side != desired_side:
            # Keep an explicit-side-conflict candidate only as a last-ditch
            # fallback when no side-matching or unknown-side routes exist.
            if best_conflict is None or any_key < best_conflict[0]:
                best_conflict = (any_key, path)
            continue
        if best_any is None or any_key < best_any[0]:
            best_any = (any_key, path)

        if desired_side:
            comm_penalty = 0 if side == desired_side else 3
            pref_key = (comm_penalty, recent_penalty, hops, -quality, target_sector)
            # Prefer explicit market-side matches only; unknown side can trap
            # stale guard in repeated non-buying/non-selling loops.
            if comm_penalty == 0 and (best_pref is None or pref_key < best_pref[0]):
                best_pref = (pref_key, path)

    # Prefer side-matched targets when possible; otherwise fall back to any known
    # port so stale/partial market intel doesn't trap guard mode in pure explores.
    best = best_pref if best_pref is not None else (best_any if best_any is not None else best_conflict)
    if best is not None:
        path = best[1]
        return TradeAction.MOVE, {
            "target_sector": int(path[-1]),
            "path": list(path),
            "urgency": "no_trade_reroute",
        }

    warps = [int(w) for w in (getattr(state, "warps", []) or []) if int(w) != current_sector]
    known_non_port = set()
    for warp in warps:
        with contextlib.suppress(Exception):
            info = knowledge.get_sector_info(int(warp))
            if info is not None and getattr(info, "has_port", None) is False:
                known_non_port.add(int(warp))
    preferred_warps = [w for w in warps if int(w) not in known_non_port]
    if preferred_warps:
        target = (
            sorted(w for w in preferred_warps if int(w) != int(previous_sector or 0))
            or sorted(preferred_warps)
        )
        return TradeAction.EXPLORE, {"direction": int(target[0]), "urgency": "no_trade_reroute"}
    if warps:
        target = sorted(w for w in warps if int(w) != int(previous_sector or 0)) or sorted(warps)
        return TradeAction.EXPLORE, {"direction": int(target[0]), "urgency": "no_trade_reroute"}
    return None


def _state_cargo_for_commodity(state, commodity: str | None) -> int | None:
    """Return on-board cargo amount for a normalized commodity token."""
    key = str(commodity or "").strip().lower()
    attr = {
        "fuel_ore": "cargo_fuel_ore",
        "organics": "cargo_organics",
        "equipment": "cargo_equipment",
    }.get(key)
    if not attr:
        return None
    with contextlib.suppress(Exception):
        return int(getattr(state, attr, 0) or 0)
    return 0


def _is_futile_sell_trade(state, params: dict | None) -> bool:
    """True when a targeted sell request has no corresponding cargo in state."""
    if not isinstance(params, dict):
        return False
    action = str(params.get("action") or "").strip().lower()
    if action != "sell":
        return False
    commodity = str(params.get("commodity") or "").strip().lower()
    qty = _state_cargo_for_commodity(state, commodity)
    return qty is not None and qty <= 0


def _choose_guard_escape_jump_target(*, current_sector: int, recent_sectors: list[int] | deque[int] | None) -> int:
    """Pick a deterministic far sector to break local no-trade loops.

    Uses coprime strides across the 1..1000 sector range while avoiding the most
    recent cycle tail when possible.
    """
    current = int(current_sector or 0)
    if current <= 0:
        return 1
    recent = [int(s) for s in (recent_sectors or []) if int(s) > 0]
    avoid = {int(s) for s in recent[-12:]}
    for stride in (137, 271, 389, 523, 719):
        candidate = ((current + stride - 1) % 1000) + 1
        if candidate != current and candidate not in avoid:
            return int(candidate)
    # Fall back to any different sector if everything in the tail is saturated.
    fallback = ((current + 137 - 1) % 1000) + 1
    return int(fallback if fallback != current else ((current % 1000) + 1))


def _find_nearest_market_path(
    *,
    state,
    knowledge,
    commodity: str,
    desired_side: str,
    max_hops: int = 12,
) -> list[int] | None:
    """Return shortest known path to a port matching commodity market side."""
    current_sector = int(getattr(state, "sector", 0) or 0)
    if current_sector <= 0:
        return None
    target_commodity = str(commodity or "").strip().lower()
    if target_commodity not in {"fuel_ore", "organics", "equipment"}:
        return None
    want_side = str(desired_side or "").strip().lower()
    if want_side not in {"buying", "selling"}:
        return None

    best: list[int] | None = None
    for sector, info in (getattr(knowledge, "_sectors", {}) or {}).items():
        try:
            target_sector = int(sector)
        except Exception:
            continue
        if target_sector <= 0 or target_sector == current_sector:
            continue
        if not getattr(info, "has_port", False):
            continue
        statuses = _derive_port_statuses(getattr(info, "port_class", None), info)
        if statuses.get(target_commodity) != want_side:
            continue
        path = knowledge.find_path(current_sector, target_sector, max_hops=max_hops)
        if not path or len(path) < 2:
            continue
        if best is None or len(path) < len(best):
            best = list(path)
    return best


def _get_zero_trade_streak(bot, sector: int, commodity: str | None = None, trade_action: str | None = None) -> int:
    """Return tracked zero-delta trade streak for a sector/commodity/action.

    If commodity/action are omitted, returns the highest streak seen in the sector.
    """
    try:
        zero_map = getattr(bot, "_zero_trade_streak", {}) or {}
    except Exception:
        return 0
    if not isinstance(zero_map, dict):
        return 0
    if int(sector or 0) <= 0:
        return 0

    if commodity is not None and trade_action is not None:
        with contextlib.suppress(Exception):
            return max(0, int(zero_map.get((int(sector), str(commodity), str(trade_action)), 0) or 0))

    best = 0
    for key, value in zero_map.items():
        try:
            sig_sector = int(key[0])
        except Exception:
            continue
        if sig_sector != int(sector):
            continue
        with contextlib.suppress(Exception):
            best = max(best, int(value or 0))
    return max(0, best)


def _is_sector_ping_pong(recent_sectors: list[int] | deque[int]) -> bool:
    """Detect short repeating movement loops (ABAB, ABCABC)."""
    seq = list(recent_sectors)
    if len(seq) < 4:
        return False

    def _repeats(cycle_len: int) -> bool:
        if len(seq) < cycle_len * 2:
            return False
        tail = seq[-(cycle_len * 2) :]
        pattern = tail[:cycle_len]
        if len(set(pattern)) <= 1:
            return False
        return tail[cycle_len:] == pattern

    return _repeats(2) or _repeats(3)


def _choose_ping_pong_break_action(
    *,
    state,
    knowledge,
    recent_sectors: list[int] | deque[int],
    turns_since_last_trade: int,
) -> tuple[TradeAction, dict] | None:
    """Return an alternate action when movement is stuck in ABAB loops."""
    if getattr(state, "context", None) != "sector_command":
        return None
    if turns_since_last_trade < 8:
        return None
    if not _is_sector_ping_pong(recent_sectors):
        return None

    current = int(getattr(state, "sector", 0) or 0)
    previous = int(list(recent_sectors)[-2]) if len(recent_sectors) >= 2 else 0
    warps = [int(w) for w in (getattr(state, "warps", []) or [])]
    if not warps and current > 0:
        known_warps = knowledge.get_warps(current) if knowledge else None
        if known_warps:
            warps = [int(w) for w in known_warps]

    if not warps:
        return None

    recent_tail = list(recent_sectors)[-6:]
    recent_block = {int(s) for s in recent_tail if int(s) != current}
    candidates = [w for w in warps if w != current and w not in recent_block]
    if not candidates:
        candidates = [w for w in warps if w != current and w != previous]
    if not candidates:
        return None

    # Prefer unknown branches to maximize map/market discovery while escaping loops.
    unseen = [w for w in candidates if knowledge and knowledge.get_warps(w) is None]
    target = sorted(unseen or candidates)[0]
    return TradeAction.EXPLORE, {"direction": target, "urgency": "loop_break"}


def _is_move_stall_recent_actions(
    recent_actions: list[dict] | None,
    *,
    min_streak: int = 8,
) -> bool:
    """True when recent actions are a non-productive MOVE/EXPLORE streak."""
    actions = list(recent_actions or [])
    if len(actions) < int(min_streak):
        return False
    tail = actions[-max(int(min_streak), 12) :]
    if len(tail) < int(min_streak):
        return False

    move_like = {"MOVE", "EXPLORE"}
    for entry in tail:
        action = str(entry.get("action") or "").strip().upper()
        if action not in move_like:
            return False
        try:
            delta = int(entry.get("result_delta") or 0)
        except Exception:
            delta = 0
        if delta != 0:
            return False
    return True


def _resolve_no_trade_guard_thresholds(
    *,
    config: BotConfig,
    turns_used: int,
    turns_since_last_trade: int,
    trades_done: int,
    credits_per_turn: float,
    trades_per_100_turns: float,
) -> tuple[int, int, bool]:
    """Return adaptive guard thresholds and whether stale-guard is enabled."""
    base_turns = max(1, int(getattr(config.trading, "no_trade_guard_turns", 60)))
    base_stale = max(1, int(getattr(config.trading, "no_trade_guard_stale_turns", base_turns)))
    if not bool(getattr(config.trading, "no_trade_guard_dynamic", True)):
        return base_turns, base_stale, True

    min_turns = max(1, int(getattr(config.trading, "no_trade_guard_turns_min", 24)))
    max_turns = max(min_turns, int(getattr(config.trading, "no_trade_guard_turns_max", 180)))
    min_stale = max(1, int(getattr(config.trading, "no_trade_guard_stale_turns_min", 24)))
    max_stale = max(min_stale, int(getattr(config.trading, "no_trade_guard_stale_turns_max", 240)))
    warmup_turns = max(0, int(getattr(config.trading, "no_trade_guard_dynamic_warmup_turns", 30)))
    stale_disable_after_trades = max(0, int(getattr(config.trading, "no_trade_guard_stale_disable_after_trades", 5)))
    stale_resume_turns = max(1, int(getattr(config.trading, "no_trade_guard_stale_resume_turns", 180)))

    # Multipliers: tighten on clear failure, relax on sustained healthy behavior.
    scale = 1.0
    if turns_used <= warmup_turns:
        scale = 2.0
    elif credits_per_turn >= 0.8 and trades_per_100_turns >= 8.0:
        scale = 2.4
    elif credits_per_turn >= 0.35 and trades_per_100_turns >= 4.0:
        scale = 1.8
    elif credits_per_turn >= 0.12 and trades_per_100_turns >= 2.0:
        scale = 1.35
    elif credits_per_turn < -0.25 and trades_per_100_turns < 1.5:
        scale = 0.70
    elif credits_per_turn < 0.0 and trades_per_100_turns < 2.5:
        scale = 0.85
    elif trades_done == 0 and turns_since_last_trade >= base_stale:
        scale = 0.65

    # Sparse trade history should not relax guard windows aggressively.
    # One early profitable trade can otherwise postpone recovery too long.
    if trades_done <= 1:
        scale = min(scale, 1.0)
        early_floor_turns = max(int(warmup_turns) + 8, 20)
        if turns_used >= early_floor_turns and turns_since_last_trade >= max(16, int(round(base_stale * 0.5))):
            scale = min(scale, 0.85)
        if trades_done == 0 and turns_since_last_trade >= max(24, int(round(base_stale * 0.6))):
            scale = min(scale, 0.70)

    guard_turns = int(round(base_turns * scale))
    guard_stale_turns = int(round(base_stale * scale))
    guard_turns = max(min_turns, min(max_turns, guard_turns))
    guard_stale_turns = max(min_stale, min(max_stale, guard_stale_turns))

    stale_guard_enabled = True
    if (
        trades_done >= stale_disable_after_trades
        and trades_per_100_turns >= 2.0
        and credits_per_turn > -0.05
    ):
        stale_guard_enabled = False
        guard_stale_turns = max(guard_stale_turns, min(max_stale, int(round(base_stale * 2.0))))

    # Safety catch: always re-enable stale guard if we have been dry for a long time.
    if turns_since_last_trade >= max(stale_resume_turns, int(round(base_stale * 2.0))):
        stale_guard_enabled = True

    return guard_turns, guard_stale_turns, stale_guard_enabled


def _compute_no_trade_guard_flags(
    *,
    config: BotConfig,
    turns_used: int,
    turns_since_last_trade: int,
    trades_done: int,
    guard_min_trades: int,
    guard_turns: int,
    guard_stale_turns: int,
    stale_guard_enabled: bool,
    credits_per_turn: float,
    trades_per_100_turns: float,
    last_stale_force_turn: int = -10_000,
) -> tuple[bool, bool, bool]:
    """Return guard activation and force-action flags.

    Returns: (force_guard, force_guard_action, stale_soft_holdoff)
    """
    hard_no_trade_guard = turns_used >= int(guard_turns) and trades_done < int(guard_min_trades)
    stale_guard_trigger = bool(stale_guard_enabled) and turns_since_last_trade >= int(guard_stale_turns)
    stale_soft_holdoff = False
    if stale_guard_trigger and not hard_no_trade_guard:
        soft_holdoff_enabled = bool(getattr(config.trading, "no_trade_guard_stale_soft_holdoff", True))
        soft_holdoff_multiplier = max(
            1.0,
            float(getattr(config.trading, "no_trade_guard_stale_soft_holdoff_multiplier", 2.2) or 2.2),
        )
        holdoff_limit = int(round(float(guard_stale_turns) * soft_holdoff_multiplier))
        healthy_history = (
            int(trades_done) >= max(3, int(guard_min_trades) + 2)
            and float(trades_per_100_turns) >= 1.4
            and float(credits_per_turn) >= -0.05
        )
        stale_soft_holdoff = soft_holdoff_enabled and healthy_history and turns_since_last_trade < holdoff_limit

    force_guard = hard_no_trade_guard or (stale_guard_trigger and not stale_soft_holdoff)
    force_guard_action = force_guard
    if force_guard and not hard_no_trade_guard:
        stale_force_interval = max(
            1,
            int(getattr(config.trading, "no_trade_guard_stale_force_interval_turns", 4) or 4),
        )
        if (int(turns_used) - int(last_stale_force_turn or -10_000)) < stale_force_interval:
            force_guard_action = False
    return force_guard, force_guard_action, stale_soft_holdoff


def _should_disable_guard_forced_trade(
    *,
    trade_attempts: int,
    trade_successes: int,
    turns_since_last_trade: int,
    guard_stale_turns: int,
    controls,
) -> bool:
    """Return True when forced no-trade probes should be suspended."""
    if not bool(getattr(controls, "forced_probe_disable_enabled", True)):
        return int(turns_since_last_trade) >= max(12, int(guard_stale_turns // 3))
    attempts = max(0, int(trade_attempts))
    successes = max(0, int(trade_successes))
    low_attempts = max(1, int(getattr(controls, "forced_probe_disable_attempts_low", 12)))
    high_attempts = max(low_attempts, int(getattr(controls, "forced_probe_disable_attempts_high", 24)))
    low_rate = max(0.0, min(1.0, float(getattr(controls, "forced_probe_disable_success_rate_low", 0.08))))
    high_rate = max(0.0, min(1.0, float(getattr(controls, "forced_probe_disable_success_rate_high", 0.12))))
    if attempts < min(10, low_attempts):
        return False
    success_rate = float(successes) / float(max(1, attempts))
    if attempts >= high_attempts and success_rate < high_rate:
        return True
    if attempts >= low_attempts and success_rate < low_rate:
        return True
    if success_rate >= 0.15:
        return False
    return int(turns_since_last_trade) >= max(12, int(guard_stale_turns // 3))


def _should_force_bootstrap_trade(
    *,
    config: BotConfig,
    turns_used: int,
    trades_done: int,
    guard_min_trades: int,
    force_guard: bool,
) -> bool:
    """Return True when we should force an early first-trade action."""
    if force_guard:
        return False
    bootstrap_turns = max(0, int(getattr(config.trading, "bootstrap_trade_turns", 12)))
    if turns_used < bootstrap_turns:
        return False
    return int(trades_done) < int(max(1, guard_min_trades))


def _is_effective_trade_change(
    *,
    credit_change: int,
    trade_action: str | None = None,
    is_buy: bool | None = None,
) -> bool:
    """Return True when credit delta matches the intended trade direction.

    BUY legs should reduce credits, SELL legs should increase credits.
    If side is unknown, any non-zero delta is treated as effective.
    """
    delta = int(credit_change)
    side_is_buy = is_buy
    if side_is_buy is None:
        side = str(trade_action or "").strip().lower()
        if side == "buy":
            side_is_buy = True
        elif side == "sell":
            side_is_buy = False

    if side_is_buy is True:
        return delta < 0
    if side_is_buy is False:
        return delta > 0
    return delta != 0


def _should_count_trade_completion(
    *,
    trade_interaction_seen: bool,
    credit_change: int,
    trade_action: str | None = None,
    is_buy: bool | None = None,
) -> bool:
    """Count completed trade telemetry only for effective executions."""
    if _is_effective_trade_change(credit_change=credit_change, trade_action=trade_action, is_buy=is_buy):
        return True
    if not trade_interaction_seen:
        return False
    return False


async def run_trading_loop(bot, config: BotConfig, char_state) -> None:
    """Run the main trading loop using the configured strategy."""
    from bbsbot.games.tw2002.strategy_manager import StrategyManager

    # Use strategy manager for rotation support
    if config.trading.enable_strategy_rotation:
        strategy_manager = StrategyManager(config, bot.sector_knowledge)
        strategy = strategy_manager.get_current_strategy(bot)
        print(f"\n[Trading] Starting with {strategy.name} strategy (rotation enabled)...")
    else:
        strategy = bot.strategy
        if not strategy:
            strategy = bot.init_strategy()
        strategy_manager = None
        print(f"\n[Trading] Starting {strategy.name} strategy...")

    target_credits = config.session.target_credits
    max_turns_config = config.session.max_turns_per_session
    max_turns = max_turns_config if max_turns_config > 0 else 999999  # Temporary, will be set from state
    server_max_turns: int | None = None  # Detected from server

    turns_used = 0
    consecutive_orient_failures = 0
    goal_status_display: GoalStatusDisplay | None = None
    last_trade_turn = int(getattr(bot, "_last_trade_turn", 0) or 0)
    recent_sectors: deque[int] = deque(maxlen=8)

    # End-state swarm behavior: never "finish" the process just because we hit a goal.
    # Goals become milestones; the bot keeps playing and self-heals if it gets knocked out.
    milestone_hits = 0

    while turns_used < max_turns:
        # Allow the Swarm Dashboard to pause automation while hijacked.
        await_if_hijacked = getattr(bot, "await_if_hijacked", None)
        if callable(await_if_hijacked):
            await await_if_hijacked()

        turns_used += 1
        bot.turns_used = turns_used

        def _refund_turn_counter() -> None:
            """Undo local turn accounting for non-turn-consuming housekeeping steps."""
            nonlocal turns_used
            turns_used = max(0, turns_used - 1)
            bot.turns_used = turns_used

        # Get current state (with scan optimization)
        orient_retries = 0
        max_orient_retries = 3
        state = None

        while orient_retries < max_orient_retries and state is None:
            try:
                state = await bot.orient()
            except Exception as e:
                # Check if we're stuck in a loop
                from bbsbot.games.tw2002 import errors

                if "Stuck in loop" in str(e) or "loop_detected" in str(e):
                    print("\n⚠️  Loop detected, attempting escape...")
                    escaped = await errors.escape_loop(bot)
                    if escaped:
                        print("  ✓ Escaped from loop, retrying orientation...")
                        orient_retries += 1
                        continue
                    else:
                        print("  ✗ Could not escape loop, skipping turn")
                        break
                transport_lost = isinstance(e, (AttributeError, RuntimeError)) and "send" in str(e).lower() and (
                    "none" in str(e).lower() or "disconnected" in str(e).lower()
                )
                if isinstance(e, (TimeoutError, ConnectionError, OrientationError)) or transport_lost:
                    # Retry on network timeouts, connection errors, and orientation failures
                    orient_retries += 1
                    if orient_retries < max_orient_retries:
                        backoff_s = orient_retries * 0.5
                        print(
                            f"\n⚠️  {type(e).__name__}, retrying ({orient_retries}/{max_orient_retries}) in {backoff_s}s..."
                        )
                        await asyncio.sleep(backoff_s)
                        continue
                    else:
                        print(f"✗ Max retries exceeded for {type(e).__name__}, skipping turn")
                        break
                else:
                    raise

        if state is None:
            # Track consecutive orient failures - try reconnection instead of exiting
            consecutive_orient_failures += 1
            if consecutive_orient_failures >= 10:
                session_obj = getattr(bot, "session", None)
                is_connected = False
                if session_obj is not None:
                    fn = getattr(session_obj, "is_connected", None)
                    if callable(fn):
                        with contextlib.suppress(Exception):
                            result = fn()
                            if not asyncio.iscoroutine(result):
                                is_connected = bool(result)
                    else:
                        is_connected = True
                if not is_connected:
                    # Connection lost - attempt reconnection instead of exiting
                    print(f"\n⚠️  Connection lost after {consecutive_orient_failures} failures, attempting reconnect...")
                    try:
                        # Reconnect to BBS using the connect() function
                        await asyncio.sleep(2)  # Wait before reconnect
                        from bbsbot.games.tw2002.connection import connect

                        await connect(bot, host=config.connection.host, port=config.connection.port)
                        print("✓ Reconnected! Resuming play...")
                        consecutive_orient_failures = 0
                        continue
                    except Exception as e:
                        print(f"✗ Reconnection failed: {e}")
                        break
                # Still connected but orient keeps failing - try full recovery
                print(f"\n⚠️  {consecutive_orient_failures} consecutive failures, attempting full recovery...")
                try:
                    await bot.recover()
                    consecutive_orient_failures = 0
                except Exception:
                    print("✗ Recovery failed, waiting before retry...")
                    await asyncio.sleep(3)
            _refund_turn_counter()
            continue

        # Successful orient - reset failure counter
        consecutive_orient_failures = 0

        # Keep strategy inputs stable even when semantic extraction misses cargo rows.
        _apply_cargo_ledger_to_state(bot, state)

        # Detect server maximum turns on first orient (if configured to use server max)
        if turns_used == 1 and max_turns_config == 0 and state.turns_left is not None:
            server_max_turns = turns_used + state.turns_left
            max_turns = server_max_turns
            logger.info(f"Detected server maximum turns: {server_max_turns}")
            print(f"  📊 Server max turns: {server_max_turns}")

        # After first successful orient, push full state to dashboard immediately
        if turns_used == 1 and hasattr(bot, "report_status"):
            await bot.report_status()

        char_state.update_from_game_state(state)
        try:
            sector_now = int(getattr(state, "sector", 0) or 0)
            if sector_now > 0:
                recent_sectors.append(sector_now)
        except Exception:
            pass

        # Update bot's current credits from state (needed for trade quantity calculations)
        if state.credits is not None:
            bot.current_credits = state.credits

        credits = state.credits or 0
        print(f"\n[Turn {turns_used}] Sector {state.sector}, Credits: {credits:,}")

        # CRITICAL: Handle game selection menu - bot should auto-enter game
        if state.context == "menu" and state.sector is None:
            # Check if this is the game selection menu by looking at screen content
            screen = bot.session.get_screen() if hasattr(bot, "session") and bot.session else ""
            screen_lower = screen.lower() if screen else ""
            is_game_selection = (
                "trade wars" in screen_lower
                or "supports up to" in screen_lower
                or "- play" in screen_lower
                or "game selection" in screen_lower
            )

            if is_game_selection and hasattr(bot, "last_game_letter") and bot.last_game_letter:
                print(f"  ⚠️  At game selection menu - entering game with '{bot.last_game_letter}'...")
                await bot.session.send(bot.last_game_letter + "\r")
                await asyncio.sleep(2.0)
                # Skip to next turn to re-orient inside the game
                _refund_turn_counter()
                continue

        # Strategy loop runs from sector command. If we're in another in-game
        # menu, send the minimal escape key and re-orient without counting a turn.
        if state.context != "sector_command":
            ctx = str(state.context or "")
            if ctx == "planet_command":
                logger.info("Exiting planet command to sector command (Q)")
                await bot.session.send("Q")
                await asyncio.sleep(0.6)
                _refund_turn_counter()
                continue
            if ctx in {"known_universe_display", "prompt.pause_simple", "pause_simple"}:
                await bot.session.send(" ")
                await asyncio.sleep(0.35)
                _refund_turn_counter()
                continue
            if ctx in {"port_menu", "bank_menu", "corporation_menu", "computer_menu", "citadel_command"}:
                await bot.session.send("Q")
                await asyncio.sleep(0.6)
                _refund_turn_counter()
                continue
            with contextlib.suppress(Exception):
                await bot.recover()
            _refund_turn_counter()
            continue

        # Show compact goal status every N turns (AI strategy only).
        try:
            show_viz = (
                config.trading.strategy == "ai_strategy"
                and config.trading.ai_strategy.show_goal_visualization
                and config.trading.ai_strategy.visualization_interval > 0
            )
        except Exception:
            show_viz = False

        if show_viz:
            phase = getattr(strategy, "_current_phase", None)
            if phase is not None:
                current_turn = getattr(strategy, "_current_turn", turns_used)
                interval = config.trading.ai_strategy.visualization_interval
                if current_turn % interval == 0:
                    if goal_status_display is None:
                        goal_status_display = GoalStatusDisplay()
                    # Use server-detected max_turns if available, else config value
                    display_max = max_turns if max_turns < 999999 else max_turns_config or 0
                    status_line = goal_status_display.render_compact(
                        phase=phase,
                        current_turn=current_turn,
                        max_turns=display_max,
                    )
                    print(f"  {status_line}")
                    emit_viz = getattr(bot, "emit_viz", None)
                    if callable(emit_viz):
                        emit_viz("compact", status_line, turn=current_turn)

        # Goal becomes a milestone; keep going.
        if credits >= target_credits:
            milestone_hits += 1
            print(f"\nMilestone reached: {credits:,} credits (target={target_credits:,})!")
            # Increase target so we don't spam this every loop.
            try:
                target_credits = max(target_credits + 100_000, int(target_credits * 1.5))
            except Exception:
                target_credits = target_credits + 100_000
            ai_activity = getattr(bot, "ai_activity", None)
            if ai_activity is not None:
                bot.ai_activity = f"MILESTONE {milestone_hits}: {credits:,} credits (next {target_credits:,})"
            await asyncio.sleep(0.5)

        # Check turns
        if state.turns_left is not None and state.turns_left <= 0:
            print("\nOut of turns. Entering idle backoff (will retry).")
            try:
                bot.ai_activity = "OUT_OF_TURNS (idle/backoff)"
                await bot.report_status()
            except Exception:
                pass
            # Turns replenish out-of-band; keep the worker alive and retry periodically.
            await asyncio.sleep(60.0)
            continue

        # Policy: per-bot selectable and can auto-switch dynamically based on bankroll.
        def _dynamic_spread_lane() -> str:
            raw = str(getattr(bot, "bot_id", "") or "")
            m = re.search(r"(\d+)\s*$", raw)
            if m:
                idx = int(m.group(1))
            elif raw:
                idx = abs(hash(raw))
            else:
                idx = 0
            return ("conservative", "balanced", "aggressive")[idx % 3]

        def _compute_policy(credits_now: int | None) -> str:
            policy = getattr(config.trading, "policy", "dynamic")
            if policy and policy != "dynamic":
                return policy
            credits_val = int(credits_now or 0)
            dyn = getattr(config.trading, "dynamic_policy", None)
            try:
                conservative_under = int(getattr(dyn, "conservative_under_credits", 300)) if dyn else 300
                aggressive_over = int(getattr(dyn, "aggressive_over_credits", 20000)) if dyn else 20000
                spread_enabled = bool(getattr(dyn, "spread_enabled", True)) if dyn else True
            except Exception:
                conservative_under = 300
                aggressive_over = 20000
                spread_enabled = True
            if credits_val < conservative_under:
                return "conservative"
            if credits_val >= aggressive_over:
                return "aggressive"
            if spread_enabled:
                return _dynamic_spread_lane()
            return "balanced"

        try:
            ai_policy_locked = bool(
                getattr(strategy, "name", "") == "ai_strategy"
                and bool(getattr(config.trading.ai_strategy, "supervisor_policy_locked", True))
            )
        except Exception:
            ai_policy_locked = False

        # Anti-waste guardrail: if we have burned many turns with very few trades,
        # force a profit-first strategy/mode to avoid long explore-only runs.
        guard_min_trades = int(getattr(config.trading, "no_trade_guard_min_trades", 1))
        guard_strategy = str(getattr(config.trading, "no_trade_guard_strategy", "profitable_pairs"))
        guard_mode = str(getattr(config.trading, "no_trade_guard_mode", "balanced"))
        trades_done = int(getattr(bot, "trades_executed", 0) or 0)
        trade_attempts_done = int(getattr(bot, "trade_attempts", 0) or 0)
        trade_successes_done = int(getattr(bot, "trade_successes", 0) or 0)
        turns_since_last_trade = turns_used if last_trade_turn <= 0 else max(0, turns_used - last_trade_turn)
        session_start_credits = getattr(bot, "_session_start_credits", None)
        credits_now = int(getattr(state, "credits", 0) or 0)
        if credits_now >= 0 and session_start_credits is None:
            with contextlib.suppress(Exception):
                bot._session_start_credits = credits_now
                session_start_credits = credits_now
        credits_per_turn = 0.0
        if credits_now >= 0 and session_start_credits is not None and turns_used > 0:
            with contextlib.suppress(Exception):
                credits_per_turn = float(int(credits_now) - int(session_start_credits)) / float(turns_used)
        if credits_per_turn == 0.0 and turns_used > 0:
            with contextlib.suppress(Exception):
                credits_per_turn = float(getattr(bot, "credits_per_turn", 0.0) or 0.0)
        trades_per_100_turns = (float(trades_done) * 100.0 / float(turns_used)) if turns_used > 0 else 0.0

        guard_turns, guard_stale_turns, stale_guard_enabled = _resolve_no_trade_guard_thresholds(
            config=config,
            turns_used=turns_used,
            turns_since_last_trade=turns_since_last_trade,
            trades_done=trades_done,
            credits_per_turn=credits_per_turn,
            trades_per_100_turns=trades_per_100_turns,
        )
        hard_no_trade_guard = turns_used >= guard_turns and trades_done < guard_min_trades
        force_guard, force_guard_action, stale_soft_holdoff = _compute_no_trade_guard_flags(
            config=config,
            turns_used=turns_used,
            turns_since_last_trade=turns_since_last_trade,
            trades_done=trades_done,
            guard_min_trades=guard_min_trades,
            guard_turns=guard_turns,
            guard_stale_turns=guard_stale_turns,
            stale_guard_enabled=stale_guard_enabled,
            credits_per_turn=credits_per_turn,
            trades_per_100_turns=trades_per_100_turns,
            last_stale_force_turn=int(getattr(bot, "_last_no_trade_stale_force_turn", -10_000) or -10_000),
        )
        no_trade_controls = resolve_anti_collapse_controls(
            config,
            getattr(getattr(config.trading, "no_trade_guard", None), "anti_collapse_override", None),
        )
        disable_forced_trade_probe = _should_disable_guard_forced_trade(
            trade_attempts=trade_attempts_done,
            trade_successes=trade_successes_done,
            turns_since_last_trade=turns_since_last_trade,
            guard_stale_turns=guard_stale_turns,
            controls=no_trade_controls,
        )
        prev_disable = bool(getattr(bot, "_anti_prev_forced_probe_disable", False))
        if disable_forced_trade_probe and not prev_disable:
            bot._anti_trigger_forced_probe_disable = int(getattr(bot, "_anti_trigger_forced_probe_disable", 0) or 0) + 1
        bot._anti_prev_forced_probe_disable = disable_forced_trade_probe
        bot._anti_forced_probe_disable_active = disable_forced_trade_probe
        if disable_forced_trade_probe and force_guard_action:
            force_guard_action = False
        force_bootstrap_trade = _should_force_bootstrap_trade(
            config=config,
            turns_used=turns_used,
            trades_done=trades_done,
            guard_min_trades=guard_min_trades,
            force_guard=force_guard,
        )
        if disable_forced_trade_probe:
            force_bootstrap_trade = False
        if stale_soft_holdoff:
            with contextlib.suppress(Exception):
                bot.strategy_intent = "RECOVERY:STALE_HOLDOFF"

        if force_guard:
            current_name = getattr(strategy, "name", "unknown")
            if current_name != guard_strategy:
                logger.warning(
                    "no_trade_guard_switch: turns=%s trades=%s from=%s to=%s",
                    turns_used,
                    trades_done,
                    current_name,
                    guard_strategy,
                )
                if strategy_manager:
                    with contextlib.suppress(Exception):
                        strategy_manager._current_strategy_name = guard_strategy
                        strategy_manager._current_strategy = strategy_manager._create_strategy(guard_strategy)
                        strategy_manager._consecutive_failures = 0
                        strategy_manager._turns_on_current_strategy = 0
                        strategy = strategy_manager._current_strategy
                else:
                    strategy = _create_strategy_instance(guard_strategy, config, bot.sector_knowledge)
                with contextlib.suppress(Exception):
                    bot._strategy = strategy
            effective_policy = guard_mode
            if trades_done <= 0 and turns_since_last_trade >= max(120, int(guard_stale_turns * 2)):
                effective_policy = "aggressive"
            with contextlib.suppress(Exception):
                if force_guard_action:
                    bot.strategy_intent = f"RECOVERY:FORCE_{guard_strategy.upper()}"
                else:
                    bot.strategy_intent = "RECOVERY:GUARD_MONITOR"
        elif ai_policy_locked:
            # End-state AI behavior: policy is controlled by AI supervisor decisions.
            effective_policy = str(getattr(strategy, "policy", None) or "balanced")
        else:
            effective_policy = _compute_policy(getattr(state, "credits", None))
            # Bootstrap bias: before first completed trade, avoid conservative mode
            # so new ships actually enter trading loops early.
            if trades_done <= 0 and effective_policy == "conservative":
                effective_policy = "balanced"
            # Throughput-aware policy overrides for dynamic mode.
            # If trade velocity is weak, bias to aggressive to increase execution.
            if (
                turns_used >= 40
                and trades_per_100_turns < 1.2
                and credits_per_turn <= 0.25
            ):
                effective_policy = "aggressive"
            # If we're losing badly on a thin bankroll, de-risk to reduce bleed.
            if (
                turns_used >= 80
                and trades_done >= 3
                and credits_now < 1_500
                and credits_per_turn < -1.5
            ):
                effective_policy = "conservative"

        try:
            if hasattr(strategy, "set_policy"):
                strategy.set_policy(effective_policy)
        except Exception:
            pass
        with contextlib.suppress(Exception):
            bot.strategy_mode = effective_policy

        # Get next action from strategy (handle async strategies)
        if hasattr(strategy, "_get_next_action_async"):
            # AIStrategy has async implementation
            action, params = await strategy._get_next_action_async(state)
        else:
            # Synchronous strategy
            action, params = strategy.get_next_action(state)
        strategy_action_name = action.name
        with contextlib.suppress(Exception):
            note_considered = getattr(bot, "note_decision_considered", None)
            if callable(note_considered):
                note_considered(strategy_action_name, 1)

        def _set_action(new_action: TradeAction, new_params: dict, reason: str) -> None:
            nonlocal action, params
            prev_action_name = getattr(action, "name", str(action))
            action = new_action
            params = new_params
            with contextlib.suppress(Exception):
                note_override = getattr(bot, "note_decision_override", None)
                if callable(note_override):
                    note_override(
                        from_action=prev_action_name,
                        to_action=getattr(action, "name", str(action)),
                        reason=reason,
                    )

        if force_guard_action:
            allow_guard_buy = bool(
                turns_since_last_trade >= max(20, int(guard_stale_turns // 2))
                or trades_done <= 1
            )
            if disable_forced_trade_probe:
                allow_guard_buy = False
            guard_overage = max(0, int(turns_since_last_trade - guard_stale_turns))
            if hard_no_trade_guard and trades_done <= 0:
                # Fresh bots can hit hard guard before stale thresholds.
                # Treat excess over hard-guard threshold as overage so recovery
                # logic can escalate to trade probes instead of move-only loops.
                guard_overage = max(guard_overage, max(0, int(turns_used - guard_turns)))
            forced = _choose_no_trade_guard_action(
                state=state,
                knowledge=bot.sector_knowledge,
                credits_now=credits_now,
                allow_buy=allow_guard_buy,
                guard_overage=guard_overage,
                previous_sector=(int(recent_sectors[-2]) if len(recent_sectors) >= 2 else None),
                recent_sectors=list(recent_sectors),
            )
            if forced is not None:
                if disable_forced_trade_probe and forced[0] == TradeAction.TRADE:
                    forced = _choose_guard_reroute_action(
                        state=state,
                        knowledge=bot.sector_knowledge,
                        previous_sector=(int(recent_sectors[-2]) if len(recent_sectors) >= 2 else None),
                        recent_sectors=list(recent_sectors),
                    )
                if forced is not None:
                    _set_action(forced[0], forced[1], "no_trade_guard_force")
                    if not hard_no_trade_guard:
                        with contextlib.suppress(Exception):
                            bot._last_no_trade_stale_force_turn = int(turns_used)
                    probe_urgency = str((params or {}).get("urgency") or "")
                    if action == TradeAction.TRADE and probe_urgency == "no_trade_probe":
                        probe_cooldown_turns = max(1, int(getattr(config.trading, "no_trade_probe_cooldown_turns", 5) or 5))
                        last_probe_turn = int(getattr(bot, "_last_no_trade_probe_turn", -10_000) or -10_000)
                        if (int(turns_used) - last_probe_turn) < probe_cooldown_turns:
                            reroute = _choose_guard_reroute_action(
                                state=state,
                                knowledge=bot.sector_knowledge,
                                previous_sector=(int(recent_sectors[-2]) if len(recent_sectors) >= 2 else None),
                                recent_sectors=list(recent_sectors),
                            )
                            if reroute is not None:
                                _set_action(reroute[0], reroute[1], "probe_cooldown_reroute")
                                with contextlib.suppress(Exception):
                                    bot.strategy_intent = "RECOVERY:PROBE_COOLDOWN_REROUTE"
                        else:
                            with contextlib.suppress(Exception):
                                bot._last_no_trade_probe_turn = int(turns_used)
                    logger.warning(
                        "no_trade_guard_force_action: turns=%s trades=%s action=%s params=%s",
                        turns_used,
                        trades_done,
                        action.name,
                        params,
                    )
                    with contextlib.suppress(Exception):
                        bot.strategy_intent = f"RECOVERY:TRADE_URGENCY {action.name}"
                    # If the exact local forced trade has produced zero-change outcomes repeatedly,
                    # reroute away from this sector instead of hammering the same prompt.
                    if action == TradeAction.TRADE:
                        try:
                            comm = str(params.get("commodity") or "")
                            act = str(params.get("action") or "")
                            sig = (int(getattr(state, "sector", 0) or 0), comm, act)
                            zero_map = getattr(bot, "_zero_trade_streak", {}) or {}
                            zero_streak = int(zero_map.get(sig, 0) or 0)
                        except Exception:
                            zero_streak = 0
                        if zero_streak >= 2:
                            reroute = _choose_guard_reroute_action(
                                state=state,
                                knowledge=bot.sector_knowledge,
                                previous_sector=(int(recent_sectors[-2]) if len(recent_sectors) >= 2 else None),
                                recent_sectors=list(recent_sectors),
                                commodity=(comm or None),
                                trade_action=(act or None),
                            )
                            if reroute is not None:
                                _set_action(reroute[0], reroute[1], "no_trade_guard_reroute")
                                logger.warning(
                                    "no_trade_guard_reroute: sector=%s commodity=%s action=%s zero_streak=%s -> %s %s",
                                    int(getattr(state, "sector", 0) or 0),
                                    comm,
                                    act,
                                    zero_streak,
                                    action.name,
                                    params,
                                )
                                with contextlib.suppress(Exception):
                                    bot.strategy_intent = "RECOVERY:REROUTE_STALE_PORT"
        elif force_bootstrap_trade:
            bootstrap_turns_cfg = max(0, int(getattr(config.trading, "bootstrap_trade_turns", 12)))
            bootstrap_overage = max(0, int(turns_used - bootstrap_turns_cfg))
            forced = _choose_no_trade_guard_action(
                state=state,
                knowledge=bot.sector_knowledge,
                credits_now=credits_now,
                # Fresh bots with empty holds must be able to do a small guarded
                # buy to bootstrap the first sell cycle; disabling buys here
                # can create long move-only loops with zero trades.
                allow_buy=True,
                guard_overage=bootstrap_overage,
                previous_sector=(int(recent_sectors[-2]) if len(recent_sectors) >= 2 else None),
                recent_sectors=list(recent_sectors),
            )
            if forced is not None:
                _set_action(forced[0], forced[1], "bootstrap_trade_force")
                logger.info(
                    "bootstrap_trade_force_action: turns=%s trades=%s action=%s params=%s",
                    turns_used,
                    trades_done,
                    action.name,
                    params,
                )
                with contextlib.suppress(Exception):
                    bot.strategy_intent = f"BOOTSTRAP:FORCE_{action.name}"

        # Even outside no-trade guard, don't hammer a dead port with repeated
        # zero-delta trades. Reroute after several consecutive no-op trades.
        if action == TradeAction.TRADE:
            try:
                sector_now = int(getattr(state, "sector", 0) or 0)
                comm = str(params.get("commodity") or "")
                act = str(params.get("action") or "")
                exact_streak = _get_zero_trade_streak(bot, sector_now, comm, act) if (comm and act) else 0
                sector_streak = _get_zero_trade_streak(bot, sector_now)
                trade_stall_reroute_streak = int(getattr(config.trading, "trade_stall_reroute_streak", 4) or 4)
                zero_streak = max(exact_streak, sector_streak)
            except Exception:
                zero_streak = 0
                trade_stall_reroute_streak = 4
                comm = ""
                act = ""
            if zero_streak >= trade_stall_reroute_streak:
                reroute = _choose_guard_reroute_action(
                    state=state,
                    knowledge=bot.sector_knowledge,
                    previous_sector=(int(recent_sectors[-2]) if len(recent_sectors) >= 2 else None),
                    recent_sectors=list(recent_sectors),
                    commodity=(comm or None),
                    trade_action=(act or None),
                )
                if reroute is not None:
                    _set_action(reroute[0], reroute[1], "trade_stall_reroute")
                    logger.warning(
                        "trade_stall_reroute: sector=%s zero_streak=%s -> %s %s",
                        int(getattr(state, "sector", 0) or 0),
                        zero_streak,
                        action.name,
                        params,
                    )
                    with contextlib.suppress(Exception):
                        bot.strategy_intent = "RECOVERY:TRADE_STALL_REROUTE"

        if action == TradeAction.TRADE and _is_futile_sell_trade(state, params):
            commodity = str((params or {}).get("commodity") or "").strip().lower()
            reroute = _choose_guard_reroute_action(
                state=state,
                knowledge=bot.sector_knowledge,
                previous_sector=(int(recent_sectors[-2]) if len(recent_sectors) >= 2 else None),
                recent_sectors=list(recent_sectors),
                commodity=(commodity or None),
                trade_action="sell",
            )
            if reroute is not None:
                _set_action(reroute[0], reroute[1], "empty_sell_reroute")
                logger.warning(
                    "skip_futile_sell_trade: sector=%s commodity=%s cargo=0 -> %s %s",
                    int(getattr(state, "sector", 0) or 0),
                    commodity,
                    action.name,
                    params,
                )
                with contextlib.suppress(Exception):
                    bot.strategy_intent = "RECOVERY:EMPTY_SELL_REROUTE"
            else:
                fallback_warps = [int(w) for w in (getattr(state, "warps", []) or []) if int(w) > 0]
                if fallback_warps:
                    previous = int(recent_sectors[-2]) if len(recent_sectors) >= 2 else 0
                    choices = [w for w in sorted(fallback_warps) if w != previous] or sorted(fallback_warps)
                    _set_action(
                        TradeAction.EXPLORE,
                        {"direction": int(choices[0]), "urgency": "empty_sell_escape"},
                        "empty_sell_escape",
                    )
                    logger.warning(
                        "skip_futile_sell_trade: sector=%s commodity=%s cargo=0 -> EXPLORE %s",
                        int(getattr(state, "sector", 0) or 0),
                        commodity,
                        params,
                    )
                    with contextlib.suppress(Exception):
                        bot.strategy_intent = "RECOVERY:EMPTY_SELL_EXPLORE"

        if action in (TradeAction.MOVE, TradeAction.EXPLORE, TradeAction.WAIT):
            forced_loop_break = _choose_ping_pong_break_action(
                state=state,
                knowledge=bot.sector_knowledge,
                recent_sectors=recent_sectors,
                turns_since_last_trade=turns_since_last_trade,
            )
            if forced_loop_break is not None:
                _set_action(forced_loop_break[0], forced_loop_break[1], "loop_break_force")
                logger.warning(
                    "loop_break_force_action: turns=%s turns_since_last_trade=%s recent=%s action=%s params=%s",
                    turns_used,
                    turns_since_last_trade,
                    list(recent_sectors),
                    action.name,
                    params,
                )
                with contextlib.suppress(Exception):
                    bot.strategy_intent = "RECOVERY:LOOP_BREAK"
            elif action in (TradeAction.MOVE, TradeAction.EXPLORE):
                if (
                    turns_since_last_trade >= max(28, int(guard_stale_turns))
                    and _is_move_stall_recent_actions(getattr(bot, "recent_actions", None), min_streak=8)
                    and not disable_forced_trade_probe
                ):
                    forced = _choose_no_trade_guard_action(
                        state=state,
                        knowledge=bot.sector_knowledge,
                        credits_now=credits_now,
                        allow_buy=True,
                        guard_overage=max(12, int(turns_since_last_trade - guard_stale_turns)),
                        previous_sector=(int(recent_sectors[-2]) if len(recent_sectors) >= 2 else None),
                        recent_sectors=list(recent_sectors),
                    )
                    if forced is not None and forced[0] == TradeAction.TRADE:
                        _set_action(forced[0], forced[1], "move_stall_force_trade")
                        logger.warning(
                            "move_stall_force_trade: turns=%s turns_since_last_trade=%s action=%s params=%s",
                            turns_used,
                            turns_since_last_trade,
                            action.name,
                            params,
                        )
                        with contextlib.suppress(Exception):
                            bot.strategy_intent = "RECOVERY:MOVE_STALL_FORCE_TRADE"

        print(f"  Strategy: {action.name}")

        # Emit a short intent string (separate from prompt_id/UI state).
        intent = None
        try:
            if action == TradeAction.TRADE:
                opp = params.get("opportunity")
                trade_action = params.get("action")
                if opp and getattr(opp, "commodity", None):
                    buy_sector = getattr(opp, "buy_sector", None)
                    sell_sector = getattr(opp, "sell_sector", None)
                    if trade_action in ("buy", "sell") and buy_sector and sell_sector:
                        intent = f"{trade_action.upper()} {opp.commodity} {buy_sector}->{sell_sector}"
                    else:
                        intent = f"TRADE {opp.commodity}"
            elif action == TradeAction.MOVE:
                target = params.get("target_sector")
                intent = f"MOVE {target}" if target else "MOVE"
            elif action == TradeAction.EXPLORE:
                direction = params.get("direction")
                intent = f"EXPLORE {direction}" if direction else "EXPLORE"
            elif action == TradeAction.BANK:
                intent = "BANK"
            elif action == TradeAction.UPGRADE:
                upgrade_type = params.get("upgrade_type")
                intent = f"UPGRADE {upgrade_type}" if upgrade_type else "UPGRADE"
            elif action == TradeAction.RETREAT:
                safe_sector = params.get("safe_sector")
                intent = f"RETREAT {safe_sector}" if safe_sector else "RETREAT"
            elif action == TradeAction.WAIT:
                intent = "WAIT"
        except Exception:
            intent = None

        # If AI delegated execution to a concrete strategy, expose that in intent.
        try:
            active_managed = getattr(strategy, "active_managed_strategy", "ai_direct")
            if getattr(strategy, "name", "") == "ai_strategy" and active_managed != "ai_direct":
                intent = f"{active_managed.upper()} | {intent or action.name}"
        except Exception:
            pass

        try:
            if hasattr(strategy, "set_intent"):
                strategy.set_intent(intent)
        except Exception:
            pass
        with contextlib.suppress(Exception):
            bot.strategy_intent = intent

        # Log AI reasoning to bot action feed and dashboard activity
        ai_reasoning = None
        if hasattr(strategy, "_last_reasoning") and strategy._last_reasoning:
            ai_reasoning = strategy._last_reasoning

        profit = 0
        success = True
        turns_counted = 1

        # Decision metadata emitted by AI orchestration (or derived from strategy state).
        decision_meta = params.get("__meta") if isinstance(params, dict) else None
        if not isinstance(decision_meta, dict):
            decision_meta = {}
        decision_source = str(decision_meta.get("decision_source") or "")
        wake_reason = str(
            decision_meta.get("wake_reason")
            or getattr(strategy, "_last_wake_reason", "")
            or ""
        )
        review_after_turns = decision_meta.get("review_after_turns")
        if review_after_turns is None:
            review_after_turns = getattr(strategy, "_last_review_after_turns", None)
        selected_strategy_meta = str(
            decision_meta.get("selected_strategy")
            or getattr(strategy, "active_managed_strategy", "")
            or getattr(strategy, "name", "")
            or ""
        )

        credits_before = int(getattr(state, "credits", 0) or 0)
        turns_before = int(turns_used)
        result_delta = 0
        bank_before = 0
        cargo_before = {
            "fuel_ore": int(getattr(state, "cargo_fuel_ore", 0) or 0),
            "organics": int(getattr(state, "cargo_organics", 0) or 0),
            "equipment": int(getattr(state, "cargo_equipment", 0) or 0),
        }
        with contextlib.suppress(Exception):
            bank_before = max(0, int(getattr(getattr(bot, "_banking", None), "bank_balance", 0) or 0))
        with contextlib.suppress(Exception):
            if hasattr(bot, "note_opportunity"):
                bot.note_opportunity("opportunities_seen", 1)
                if action != TradeAction.WAIT:
                    bot.note_opportunity("opportunities_executable", 1)

        # Log action to bot's action feed (if worker bot)
        import time

        if hasattr(bot, "log_action"):
            bot.current_action = action.name
            bot.current_action_time = time.time()
            # Log AI decision with reasoning
            if ai_reasoning:
                bot.log_action(
                    action=f"AI:{action.name}",
                    sector=state.sector,
                    details=ai_reasoning[:200],
                    result="pending",
                    why=ai_reasoning[:200],
                    strategy_id=selected_strategy_meta or None,
                    strategy_mode=effective_policy,
                    strategy_intent=intent,
                    wake_reason=wake_reason or None,
                    review_after_turns=review_after_turns,
                    decision_source=decision_source or None,
                    credits_before=credits_before,
                    turns_before=turns_before,
                )
                # Set activity context with AI reasoning for dashboard
                bot.ai_activity = f"AI: {action.name} ({ai_reasoning[:80]})"

        # Execute action with error recovery
        trades_before_action = int(getattr(bot, "trades_executed", 0) or 0)
        action_started_at = time.monotonic()
        with contextlib.suppress(Exception):
            note_executed = getattr(bot, "note_decision_executed", None)
            if callable(note_executed):
                note_executed(action.name, 1)
        try:
            # Pause again right before acting (lets hijack take effect between planning and acting).
            await_if_hijacked2 = getattr(bot, "await_if_hijacked", None)
            if callable(await_if_hijacked2):
                await await_if_hijacked2()

            if action == TradeAction.TRADE:
                with contextlib.suppress(Exception):
                    if hasattr(bot, "note_opportunity"):
                        bot.note_opportunity("opportunities_attempted", 1)
                opportunity = params.get("opportunity")
                trade_action = params.get("action")  # "buy" or "sell" for pair trading
                commodity = opportunity.commodity if opportunity else params.get("commodity")
                pair_signature = None
                if opportunity is not None:
                    with contextlib.suppress(Exception):
                        pair_signature = (
                            f"{int(getattr(opportunity, 'buy_sector', 0) or 0)}"
                            f"->{int(getattr(opportunity, 'sell_sector', 0) or 0)}"
                            f":{str(getattr(opportunity, 'commodity', '') or '').strip().lower() or 'unknown'}"
                        )

                if commodity:
                    print(f"  Trading {commodity} at sector {state.sector} (credits: {bot.current_credits or 0:,})")
                    max_qty = 0
                    try:
                        max_qty = int(params.get("max_quantity") or 0)
                    except Exception:
                        max_qty = 0
                    profit = await execute_port_trade(
                        bot,
                        commodity=commodity,
                        trade_action=trade_action,
                        max_quantity=max_qty,
                        pair_signature=pair_signature,
                    )
                    if profit != 0:
                        char_state.record_trade(profit)
                        print(f"  Result: {profit:+,} credits")
                        result_delta = int(profit)
                    else:
                        print("  No trade executed")
                        success = False
                else:
                    print(f"  Trading all commodities at sector {state.sector} (credits: {bot.current_credits or 0:,})")
                    profit = await execute_port_trade(bot, commodity=None, pair_signature=pair_signature)
                    if profit != 0:
                        char_state.record_trade(profit)
                        print(f"  Result: {profit:+,} credits")
                        result_delta = int(profit)
                    else:
                        print("  No trade executed")
                        success = False

            elif action == TradeAction.MOVE:
                target = params.get("target_sector")
                path = params.get("path")
                from_sector = state.sector
                if path and len(path) > 1:
                    print(f"  Navigating: {' -> '.join(str(s) for s in path)}")
                    success = await warp_along_path(bot, path)
                elif target:
                    print(f"  Moving to sector {target}")
                    success = await warp_to_sector(bot, target)

            elif action == TradeAction.EXPLORE:
                direction = params.get("direction")
                from_sector = state.sector
                if direction:
                    print(f"  Exploring sector {direction}")
                    success = await warp_to_sector(bot, direction)

            elif action == TradeAction.BANK:
                print("  Banking credits...")
                result = await bot.banking.deposit(bot, state)
                if result.success:
                    print(f"  Deposited {result.deposited:,}")

            elif action == TradeAction.UPGRADE:
                upgrade_type = params.get("upgrade_type")
                print(f"  Upgrading: {upgrade_type} (not yet implemented)")

            elif action == TradeAction.RETREAT:
                safe_sector = params.get("safe_sector")
                if safe_sector:
                    print(f"  Retreating to sector {safe_sector}")
                    await warp_to_sector(bot, safe_sector)

            elif action == TradeAction.WAIT:
                with contextlib.suppress(Exception):
                    if hasattr(bot, "note_opportunity"):
                        if int(getattr(state, "turns_left", 0) or 0) <= 0:
                            bot.note_opportunity("skipped_no_turns", 1)
                        if int(getattr(state, "holds_free", 0) or 0) <= 0:
                            bot.note_opportunity("skipped_no_holds", 1)
                print("  No action available, exploring randomly")
                warps = list(state.warps or [])
                if not warps and state.sector is not None:
                    known_warps = bot.sector_knowledge.get_warps(int(state.sector))
                    if known_warps:
                        warps = list(known_warps)
                if warps:
                    with contextlib.suppress(Exception):
                        bot._wait_no_warp_streak = 0
                    target = random.choice(warps)
                    print(f"  WAIT fallback move to sector {target}")
                    success = await warp_to_sector(bot, target)
                else:
                    # No actionable movement data. Rescan local sector to recover
                    # warps/port context and avoid indefinite WAIT deadlocks.
                    wait_streak = int(getattr(bot, "_wait_no_warp_streak", 0) or 0) + 1
                    with contextlib.suppress(Exception):
                        bot._wait_no_warp_streak = wait_streak
                    # Avoid burning synthetic turns for a brief recovery window.
                    # If recovery keeps failing, count the turn so stale-guard can fire.
                    turns_counted = 0 if wait_streak <= 2 else 1
                    success = False
                    print(f"  No warps available; attempting recovery scan (streak={wait_streak})")
                    with contextlib.suppress(Exception):
                        await bot.session.send("d")
                        await asyncio.sleep(0.4)
                        await bot.session.wait_for_update(timeout_ms=1200)
                    with contextlib.suppress(Exception):
                        await bot.recover()

            elif action == TradeAction.DONE:
                print("  Strategy complete")
                break
        except Exception as e:
            print(f"  ⚠️  Action failed: {type(e).__name__}: {e}")
            success = False
        finally:
            elapsed_ms = int(max(0.0, (time.monotonic() - action_started_at) * 1000.0))
            latency_bucket = "recovery" if str(intent or "").upper().startswith(("RECOVERY:", "BOOTSTRAP:")) else "move"
            if action == TradeAction.TRADE:
                latency_bucket = "trade"
            elif action == TradeAction.RETREAT:
                latency_bucket = "recovery"
            with contextlib.suppress(Exception):
                if hasattr(bot, "note_action_latency"):
                    bot.note_action_latency(latency_bucket, elapsed_ms)

        # Log action to bot's action feed (if worker bot)
        if hasattr(bot, "log_action"):
            details = None
            if action == TradeAction.TRADE:
                commodity = params.get("commodity")
                details = commodity or "all_commodities"
            elif action in (TradeAction.MOVE, TradeAction.EXPLORE):
                target = params.get("target_sector") or params.get("direction")
                details = str(target)

            credits_after = int(getattr(bot, "current_credits", credits_before) or credits_before)
            if credits_after <= 0 and credits_before > 0 and result_delta != 0:
                credits_after = credits_before + int(result_delta)
            turns_after = int(turns_used + max(0, turns_counted))

            bot.log_action(
                action=action.name,
                sector=state.sector,
                details=details,
                result="success" if success else "failure",
                why=ai_reasoning or intent,
                strategy_id=selected_strategy_meta or None,
                strategy_mode=effective_policy,
                strategy_intent=intent,
                wake_reason=wake_reason or None,
                review_after_turns=review_after_turns,
                decision_source=decision_source or None,
                credits_before=credits_before,
                credits_after=credits_after,
                turns_before=turns_before,
                turns_after=turns_after,
                result_delta=int(result_delta),
            )

        # Keep turns metrics tied to real game actions. A WAIT with no available
        # movement/recovery data is a no-op and should not advance turns.
        if turns_counted == 0:
            turns_used = max(0, turns_used - 1)
            bot.turns_used = turns_used

        # Track last successful trade turn for stale-trade guard.
        trades_after_action = int(getattr(bot, "trades_executed", 0) or 0)
        if trades_after_action > trades_before_action:
            last_trade_turn = int(turns_used)
            bot._last_trade_turn = last_trade_turn

        trade_meta = {}
        if action == TradeAction.TRADE:
            raw_meta = getattr(bot, "_last_trade_meta", None)
            if isinstance(raw_meta, dict):
                trade_meta = raw_meta
            with contextlib.suppress(Exception):
                if hasattr(bot, "note_opportunity") and bool(trade_meta.get("trade_success")):
                    bot.note_opportunity("opportunities_executed", 1)
                if hasattr(bot, "note_opportunity") and str(trade_meta.get("trade_failure_reason") or "") == "no_port":
                    bot.note_opportunity("skipped_no_port", 1)
        elif action == TradeAction.RETREAT:
            with contextlib.suppress(Exception):
                if hasattr(bot, "note_opportunity"):
                    bot.note_opportunity("skipped_risk", 1)

        credits_after_obs = int(getattr(bot, "current_credits", credits_before) or credits_before)
        bank_after = 0
        with contextlib.suppress(Exception):
            bank_after = max(0, int(getattr(getattr(bot, "_banking", None), "bank_balance", 0) or 0))
        post_state = getattr(bot, "game_state", None)
        cargo_after = {
            "fuel_ore": int(getattr(post_state, "cargo_fuel_ore", 0) or 0),
            "organics": int(getattr(post_state, "cargo_organics", 0) or 0),
            "equipment": int(getattr(post_state, "cargo_equipment", 0) or 0),
        }
        combat_evidence = bool(
            str(getattr(state, "context", "") or "").strip().lower() == "combat"
            or int(getattr(state, "hostile_fighters", 0) or 0) > 0
            or str(getattr(post_state, "context", "") or "").strip().lower() == "combat"
            or int(getattr(post_state, "hostile_fighters", 0) or 0) > 0
        )
        with contextlib.suppress(Exception):
            if hasattr(bot, "note_action_completion"):
                bot.note_action_completion(
                    action=action.name,
                    credits_before=int(credits_before),
                    credits_after=int(credits_after_obs),
                    bank_before=int(bank_before),
                    bank_after=int(bank_after),
                    cargo_before=dict(cargo_before),
                    cargo_after=dict(cargo_after),
                    trade_attempted=bool(trade_meta.get("trade_attempted", action == TradeAction.TRADE)),
                    trade_success=bool(trade_meta.get("trade_success", success)),
                    combat_evidence=bool(combat_evidence),
                )
        result = TradeResult(
            success=success,
            action=action,
            profit=profit,
            new_sector=bot.current_sector,
            turns_used=turns_counted,
            trade_attempted=bool(trade_meta.get("trade_attempted", action == TradeAction.TRADE)),
            trade_failure_reason=str(trade_meta.get("trade_failure_reason") or ""),
            pair_signature=str(trade_meta.get("pair_signature") or ""),
            trade_commodity=str(trade_meta.get("trade_commodity") or ""),
            trade_side=str(trade_meta.get("trade_side") or ""),
            trade_sector=(
                int(trade_meta.get("trade_sector") or 0)
                if trade_meta.get("trade_sector") is not None
                else None
            ),
        )

        # Add from/to sector for failed warp tracking
        if action in (TradeAction.EXPLORE, TradeAction.MOVE):
            result.from_sector = from_sector
            if action == TradeAction.EXPLORE:
                result.to_sector = params.get("direction")
            elif action == TradeAction.MOVE:
                result.to_sector = params.get("target_sector")

        # Record result and check for strategy rotation
        strategy.record_result(result)
        if strategy_manager:
            strategy_manager.record_result(result)
            # Update strategy reference if rotation occurred
            new_strategy = strategy_manager.get_current_strategy(bot)
            if new_strategy != strategy:
                strategy = new_strategy
                print(f"\n[Strategy] Switched to {strategy.name} due to failures")

        await asyncio.sleep(0.2)


async def execute_port_trade(
    bot,
    commodity: str | None = None,
    max_quantity: int = 0,
    trade_action: str | None = None,  # "buy" | "sell" (best-effort)
    pair_signature: str | None = None,
) -> int:
    """Execute a trade at the current port.

    Docks at the port and trades commodities. If a specific commodity is given,
    only that commodity is traded (others are skipped with 0). If no commodity
    is specified, all available commodities are traded at defaults.

    Uses pending_trade tracking to avoid responding to stale price prompts
    in the screen buffer when a commodity was skipped (entered 0).

    Args:
        bot: TradingBot instance
        commodity: Target commodity ("fuel_ore", "organics", "equipment") or None for all
        max_quantity: Max quantity to trade (0 = accept game default/max)
        trade_action: If set, only act on prompts matching this action ("buy" or "sell")

    Returns:
        Credit change (positive = profit, negative = loss)
    """
    from bbsbot.games.tw2002 import errors

    def _is_qty_prompt(last_line: str) -> bool:
        return _is_port_qty_prompt(last_line)

    initial_credits = bot.current_credits or 0
    start_sector = 0
    with contextlib.suppress(Exception):
        start_sector = int(getattr(bot, "current_sector", 0) or 0)
    if start_sector <= 0:
        with contextlib.suppress(Exception):
            start_sector = int(getattr(getattr(bot, "game_state", None), "sector", 0) or 0)
    pending_trade = False
    target_re = _COMMODITY_PATTERNS.get(commodity) if commodity else None
    credits_available: int | None = None
    last_trade_commodity: str | None = None
    last_trade_is_buy: bool | None = None  # True when we are buying from port (port sells)
    last_trade_qty: int | None = None

    # Note: we cannot reliably know per-commodity cargo from the sector command prompt.
    # Only skip sells when the port prompt itself shows we have 0 in holds.

    # Guardrails for haggle loops when the bot doesn't have enough credits.
    offered_all_credits: bool = False
    insufficient_haggle_loops: int = 0

    # Bounded, policy-dependent negotiation state for the current commodity trade.
    haggle_attempts: int = 0
    last_default_offer: int | None = None
    last_offer_sent: int | None = None
    trade_interaction_seen: bool = False
    last_requested_qty: int | None = None
    attempted_trade: bool = False
    target_action_mismatch_count: int = 0
    target_action_mismatch_limit: int = 2
    non_target_prompt_count: int = 0
    non_target_prompt_limit: int = 3
    trade_failure_reason: str | None = None

    def _set_trade_failure_reason(reason: str | None) -> None:
        nonlocal trade_failure_reason
        token = str(reason or "").strip().lower()
        if token and not trade_failure_reason:
            trade_failure_reason = token

    def _publish_trade_meta(
        *,
        success: bool,
        attempted: bool,
        credit_change: int,
        sector: int,
        resolved_commodity: str | None,
        resolved_is_buy: bool | None,
    ) -> None:
        side = "unknown"
        if resolved_is_buy is True:
            side = "buy"
        elif resolved_is_buy is False:
            side = "sell"
        elif trade_action in ("buy", "sell"):
            side = str(trade_action)
        with contextlib.suppress(Exception):
            bot._last_trade_meta = {
                "trade_attempted": bool(attempted),
                "trade_success": bool(success),
                "trade_failure_reason": str(trade_failure_reason or ""),
                "pair_signature": str(pair_signature or ""),
                "trade_commodity": str(resolved_commodity or commodity or "all").strip().lower() or "all",
                "trade_side": side,
                "trade_sector": int(sector or 0),
                "trade_credit_change": int(credit_change),
            }

    def _safe_buy_qty(
        *,
        desired_qty: int,
        commodity_name: str | None,
        credits_hint: int | None,
    ) -> int:
        """Choose a buy quantity that is safe but not overly throttled."""
        qty = max(0, int(desired_qty))
        if qty <= 0:
            return 0
        if credits_hint is None:
            # Unknown credits: keep a modest probe size instead of hard-clamping to 1.
            return min(qty, 3)
        credits_val = max(0, int(credits_hint))
        if credits_val <= 0:
            return 0
        # Early-game bankrolls need constrained sizing to avoid insufficient-credit loops.
        # Use known local unit price when available; otherwise cap to a small probe batch.
        if credits_val < 1000:
            unit_price = None
            with contextlib.suppress(Exception):
                if commodity_name and getattr(bot, "sector_knowledge", None) and getattr(bot, "current_sector", None):
                    info = bot.sector_knowledge.get_sector_info(int(bot.current_sector))
                    if info:
                        quote = ((info.port_prices or {}).get(commodity_name) or {}).get("sell")
                        if quote is not None:
                            unit_price = int(quote)
            if unit_price and unit_price > 0:
                affordable = max(0, credits_val // unit_price)
                if affordable <= 0:
                    return 0
                return max(1, min(qty, affordable))
            return min(qty, 3)
        return qty

    def _infer_qty_from_credit_change(
        *,
        commodity_name: str | None,
        is_buy_side: bool | None,
        credit_delta: int,
        sector_hint: int,
    ) -> int:
        """Infer quantity when port prompt parsing misses an explicit unit count."""
        if not commodity_name or is_buy_side is None:
            return 0
        if commodity_name not in {"fuel_ore", "organics", "equipment"}:
            return 0
        if credit_delta == 0:
            return 0
        if is_buy_side and credit_delta >= 0:
            return 0
        if (not is_buy_side) and credit_delta <= 0:
            return 0

        unit_candidates: list[int] = []
        with contextlib.suppress(Exception):
            info = None
            if getattr(bot, "sector_knowledge", None) is not None and int(sector_hint or 0) > 0:
                info = bot.sector_knowledge.get_sector_info(int(sector_hint))
            if info:
                price_row = (info.port_prices or {}).get(commodity_name) or {}
                unit = int(price_row.get("sell") or 0) if is_buy_side else int(price_row.get("buy") or 0)
                if unit > 0:
                    unit_candidates.append(unit)
        with contextlib.suppress(Exception):
            hints = getattr(bot, "_cargo_value_hints", None)
            hint_unit = int((hints or {}).get(commodity_name) or 0)
            if hint_unit > 0:
                unit_candidates.append(hint_unit)

        abs_delta = abs(int(credit_delta))
        for unit in unit_candidates:
            if unit <= 0:
                continue
            qty = max(1, abs_delta // unit)
            if qty > 0:
                return int(min(200, qty))
        return 1 if abs_delta > 0 else 0

    with contextlib.suppress(Exception):
        bot._last_trade_meta = {}

    # Trade preflight: don't dock/trade from transition/menu prompts.
    # Acting from yes/no/navpoint/stop prompts can cause false no-port updates.
    with contextlib.suppress(Exception):
        from bbsbot.games.tw2002 import orientation

        quick = await orientation.where_am_i(bot, timeout_ms=100)
        if quick.context not in ("sector_command", "citadel_command"):
            logger.warning(
                "trade_preflight_recover: context=%s prompt_id=%s sector=%s",
                quick.context,
                quick.prompt_id,
                quick.sector,
            )
            await bot.recover()
            quick = await orientation.where_am_i(bot, timeout_ms=150)
        if quick.context not in ("sector_command", "citadel_command"):
            _set_trade_failure_reason("no_interaction")
            if hasattr(bot, "note_trade_telemetry"):
                bot.note_trade_telemetry("trade_attempts", 1)
                bot.note_trade_telemetry("trade_fail_no_interaction", 1)
            _publish_trade_meta(
                success=False,
                attempted=True,
                credit_change=0,
                sector=int(getattr(quick, "sector", 0) or start_sector or 0),
                resolved_commodity=commodity,
                resolved_is_buy=(trade_action == "buy") if trade_action in ("buy", "sell") else None,
            )
            return 0

    # Dock at port
    await bot.session.send("P")
    await asyncio.sleep(1.0)

    await bot.session.wait_for_update(timeout_ms=2000)
    screen = bot.session.snapshot().get("screen", "").lower()

    if "no port" in screen:
        _set_trade_failure_reason("no_port")
        # Universe/server resets can invalidate cached port data.
        # Mark this sector as non-port to avoid repeated forced-trade loops here.
        with contextlib.suppress(Exception):
            sector_now = int(getattr(bot, "current_sector", 0) or 0)
            if sector_now <= 0 and getattr(bot, "game_state", None) is not None:
                sector_now = int(getattr(bot.game_state, "sector", 0) or 0)
            if sector_now > 0 and getattr(bot, "sector_knowledge", None) is not None:
                known_info = bot.sector_knowledge.get_sector_info(sector_now)
                was_known_port = bool(getattr(known_info, "has_port", False))
                bot.sector_knowledge.update_sector(
                    sector_now,
                    {
                        "has_port": False,
                        "port_class": None,
                        "port_status": {},
                        "port_prices": {},
                        "port_trading_units": {},
                        "port_pct_max": {},
                        "port_market_ts": {},
                    },
                )
                logger.info("Marked sector as no-port after dock failure: sector=%s", sector_now)
                with contextlib.suppress(Exception):
                    if hasattr(getattr(bot, "_strategy", None), "invalidate_pairs"):
                        bot._strategy.invalidate_pairs()
                if was_known_port:
                    mismatch_count = int(getattr(bot, "_port_mismatch_count", 0) or 0) + 1
                    mismatch_sectors = set(getattr(bot, "_port_mismatch_sectors", set()) or set())
                    mismatch_sectors.add(sector_now)
                    bot._port_mismatch_count = mismatch_count
                    bot._port_mismatch_sectors = mismatch_sectors

                    # Repeated "known port -> no port" mismatches indicate stale market cache
                    # (common after server reset). Reset cached port intel once per session.
                    if (
                        not bool(getattr(bot, "_market_intel_reset_done", False))
                        and mismatch_count >= 3
                        and len(mismatch_sectors) >= 2
                    ):
                        changed = int(bot.sector_knowledge.clear_port_intel(clear_has_port=True) or 0)
                        bot._market_intel_reset_done = True
                        with contextlib.suppress(Exception):
                            if hasattr(getattr(bot, "_strategy", None), "invalidate_pairs"):
                                bot._strategy.invalidate_pairs()
                        logger.warning(
                            "market_intel_reset_due_to_port_mismatch: mismatches=%s sectors=%s cleared=%s",
                            mismatch_count,
                            len(mismatch_sectors),
                            changed,
                        )
        await bot.recover()
        if hasattr(bot, "note_trade_telemetry"):
            bot.note_trade_telemetry("trade_attempts", 1)
            bot.note_trade_telemetry("trade_fail_no_port", 1)
        _publish_trade_meta(
            success=False,
            attempted=True,
            credit_change=0,
            sector=int(start_sector or 0),
            resolved_commodity=commodity,
            resolved_is_buy=(trade_action == "buy") if trade_action in ("buy", "sell") else None,
        )
        return 0

    # Start trading (T for transaction)
    await bot.session.send("T")
    await asyncio.sleep(1.5)
    attempted_trade = True

    for step in range(30):
        await bot.session.wait_for_update(timeout_ms=2000)
        screen = bot.session.snapshot().get("screen", "")
        screen_lower = screen.lower()

        # Keep a running credits estimate from the live screen. This is more
        # reliable than cached state during login/orientation/trade screens.
        m_credits = re.search(r"\byou (?:only )?have\s+([\d,]+)\s+credits\b", screen_lower)
        if m_credits:
            with contextlib.suppress(Exception):
                credits_available = int(m_credits.group(1).replace(",", ""))

        # Check for error loops (e.g., "not in corporation" repeated)
        if errors._check_for_error_loop(bot, screen):
            logger.warning("error_loop_in_trading: step=%d", step)
            await errors.escape_loop(bot)
            break

        # Use last lines to detect current prompt state
        lines = [line.strip() for line in screen.split("\n") if line.strip()]
        last_lines = "\n".join(lines[-6:]).lower() if lines else ""
        last_line = lines[-1].strip().lower() if lines else ""

        # Back at sector command = done trading
        if re.search(r"command.*\[\d+\].*\?", last_lines):
            break

        # Port menu [T] or [Q] = not yet trading or done
        if re.search(r"\[t\]", last_lines) and "transaction" in last_lines:
            # At port menu, need to press T
            await bot.session.send("T")
            await asyncio.sleep(1.0)
            continue

        # Quantity prompt: "How many holds of X do you want to buy/sell?"
        if _is_qty_prompt(last_line):
            attempted_trade = True
            offered_all_credits = False
            insufficient_haggle_loops = 0
            haggle_attempts = 0
            last_default_offer = None
            last_offer_sent = None

            # Find the "how many" line to identify the commodity
            prompt_line = last_line
            is_buy = " buy" in prompt_line or prompt_line.strip().startswith("how many") and " buy" in prompt_line
            is_sell = " sell" in prompt_line
            prompt_qty_cap = _extract_port_qty_cap(prompt_line, screen, is_sell=is_sell)
            last_trade_is_buy = True if is_buy else (False if is_sell else None)
            last_trade_qty = None

            # Identify commodity from the prompt line (best-effort).
            if "fuel" in prompt_line:
                last_trade_commodity = "fuel_ore"
            elif "organic" in prompt_line:
                last_trade_commodity = "organics"
            elif "equip" in prompt_line:
                last_trade_commodity = "equipment"
            else:
                last_trade_commodity = commodity

            if target_re:
                # Targeted trading: only trade the target commodity
                is_target = bool(target_re.search(prompt_line))
                if is_target:
                    non_target_prompt_count = 0
                    # If the caller specified buy/sell, enforce it.
                    if trade_action == "buy" and not is_buy:
                        _set_trade_failure_reason("wrong_side")
                        await bot.session.send("0\r")
                        pending_trade = False
                        target_action_mismatch_count += 1
                        logger.debug("Skipping target commodity due to action mismatch (wanted=buy)")
                        if target_action_mismatch_count >= target_action_mismatch_limit:
                            logger.warning(
                                "Aborting targeted trade after repeated action mismatch: target=%s action=%s",
                                commodity,
                                trade_action,
                            )
                            _set_trade_failure_reason("action_mismatch")
                            await bot.session.send("Q\r")
                            await asyncio.sleep(0.5)
                            break
                        await asyncio.sleep(0.3)
                        continue
                    if trade_action == "sell" and not is_sell:
                        _set_trade_failure_reason("wrong_side")
                        await bot.session.send("0\r")
                        pending_trade = False
                        target_action_mismatch_count += 1
                        logger.debug("Skipping target commodity due to action mismatch (wanted=sell)")
                        if target_action_mismatch_count >= target_action_mismatch_limit:
                            logger.warning(
                                "Aborting targeted trade after repeated action mismatch: target=%s action=%s",
                                commodity,
                                trade_action,
                            )
                            _set_trade_failure_reason("action_mismatch")
                            await bot.session.send("Q\r")
                            await asyncio.sleep(0.5)
                            break
                        await asyncio.sleep(0.3)
                        continue

                    # If we're trying to sell but the port reports we have none, skip.
                    if trade_action == "sell" and "you have 0 in your holds" in screen_lower:
                        _set_trade_failure_reason("no_cargo")
                        await bot.session.send("0\r")
                        pending_trade = False
                        logger.debug("Skipping sell: no cargo in holds")
                        await asyncio.sleep(0.3)
                        continue

                    target_action_mismatch_count = 0
                    if max_quantity > 0:
                        effective_max_quantity = max_quantity
                        if prompt_qty_cap is not None:
                            effective_max_quantity = min(effective_max_quantity, int(prompt_qty_cap))
                        if is_buy:
                            qty_val = _safe_buy_qty(
                                desired_qty=effective_max_quantity,
                                commodity_name=last_trade_commodity,
                                credits_hint=credits_available,
                            )
                            qty_str = str(qty_val) if qty_val > 0 else "0"
                        else:
                            qty_str = str(effective_max_quantity)
                    else:
                        # Always send an explicit buy quantity; default/max can be too
                        # large and causes low-credit haggle loops on many servers.
                        if is_buy:
                            desired_qty = int(prompt_qty_cap) if prompt_qty_cap is not None else 6
                            qty_val = _safe_buy_qty(
                                desired_qty=max(1, desired_qty),
                                commodity_name=last_trade_commodity,
                                credits_hint=credits_available,
                            )
                            qty_str = str(qty_val) if qty_val > 0 else "0"
                        else:
                            qty_str = ""
                    with contextlib.suppress(Exception):
                        if qty_str.strip():
                            last_requested_qty = max(0, int(qty_str.strip()))
                            trade_interaction_seen = last_requested_qty > 0
                        elif prompt_qty_cap is not None:
                            # Empty submit accepts bracket default; keep this as
                            # quantity hint so quote parsing can still derive unit price.
                            last_requested_qty = max(0, int(prompt_qty_cap))
                            trade_interaction_seen = last_requested_qty > 0
                    await bot.session.send(f"{qty_str}\r")
                    pending_trade = True
                    logger.debug("Trading %s (qty=%s)", commodity, qty_str or "max")
                else:
                    # Strict targeted trade: skip anything that's not the target to avoid
                    # buying/selling unintended commodities (and getting stuck haggling).
                    # Non-target prompts are normal; they should not be counted as wrong-side
                    # failures for the selected commodity pair.
                    trade_interaction_seen = True
                    non_target_prompt_count += 1
                    if non_target_prompt_count >= non_target_prompt_limit:
                        logger.warning(
                            "Aborting targeted trade after repeated non-target prompts: target=%s action=%s count=%s",
                            commodity,
                            trade_action,
                            non_target_prompt_count,
                        )
                        _set_trade_failure_reason("no_target_commodity")
                        await bot.session.send("Q\r")
                        await asyncio.sleep(0.5)
                        break
                    await bot.session.send("0\r")
                    pending_trade = False
                    logger.debug("Skipping non-target commodity (target=%s)", commodity)
            else:
                # Trade all: avoid buys when credits are very low; still allow sells.
                if max_quantity > 0:
                    effective_max_quantity = max_quantity
                    if prompt_qty_cap is not None:
                        effective_max_quantity = min(effective_max_quantity, int(prompt_qty_cap))
                    if is_buy:
                        qty_val = _safe_buy_qty(
                            desired_qty=effective_max_quantity,
                            commodity_name=last_trade_commodity,
                            credits_hint=credits_available,
                        )
                        with contextlib.suppress(Exception):
                            last_requested_qty = max(0, int(qty_val))
                            trade_interaction_seen = last_requested_qty > 0
                        await bot.session.send(f"{qty_val}\r" if qty_val > 0 else "0\r")
                    else:
                        with contextlib.suppress(Exception):
                            last_requested_qty = max(0, int(effective_max_quantity))
                            trade_interaction_seen = last_requested_qty > 0
                        await bot.session.send(f"{effective_max_quantity}\r")
                else:
                    # Always send explicit buy quantity to avoid default/max over-asks.
                    if is_buy:
                        desired_qty = int(prompt_qty_cap) if prompt_qty_cap is not None else 6
                        qty_val = _safe_buy_qty(
                            desired_qty=max(1, desired_qty),
                            commodity_name=last_trade_commodity,
                            credits_hint=credits_available,
                        )
                        qty_str = str(qty_val) if qty_val > 0 else "0"
                    else:
                        qty_str = ""
                    with contextlib.suppress(Exception):
                        if qty_str.strip():
                            last_requested_qty = max(0, int(qty_str.strip()))
                            trade_interaction_seen = last_requested_qty > 0
                        elif prompt_qty_cap is not None:
                            # Empty submit accepts bracket default; keep this as
                            # quantity hint so quote parsing can still derive unit price.
                            last_requested_qty = max(0, int(prompt_qty_cap))
                            trade_interaction_seen = last_requested_qty > 0
                    await bot.session.send(f"{qty_str}\r")
                pending_trade = True

            await asyncio.sleep(0.5)
            continue

        # Capture "Agreed, N units." to compute per-unit pricing when the total appears.
        m_agreed = re.search(r"(?i)\bagreed,\s*([\d,]+)\s+units\b", last_lines)
        if m_agreed:
            with contextlib.suppress(Exception):
                last_trade_qty = int(m_agreed.group(1).replace(",", ""))
                if int(last_trade_qty or 0) > 0:
                    trade_interaction_seen = True

        # Price/offer negotiation - only respond if we have a pending trade
        if pending_trade and ("offer" in last_lines or "price" in last_lines or "haggl" in last_lines):
            attempted_trade = True
            trade_interaction_seen = True
            # Avoid getting stuck at "Your offer [X] ?" when credits are insufficient.
            default_offer: int | None = None
            m_offer = re.search(r"your offer\s*\[(\d+)\]", last_lines)
            if m_offer:
                try:
                    default_offer = int(m_offer.group(1))
                except Exception:
                    default_offer = None

            screen_insufficient = "you only have" in screen_lower
            offer_too_high = (
                credits_available is not None and default_offer is not None and default_offer > credits_available
            )

            if screen_insufficient or offer_too_high:
                if hasattr(bot, "note_trade_telemetry"):
                    bot.note_trade_telemetry("haggle_too_high", 1)
                insufficient_haggle_loops += 1
                if credits_available is not None and not offered_all_credits:
                    offered_all_credits = True
                    logger.info(
                        "Haggle default too high (default=%s credits=%s); offering all credits",
                        default_offer,
                        credits_available,
                    )
                    await bot.session.send(f"{credits_available}\r")
                    await asyncio.sleep(0.5)
                    continue

                # If offering all credits didn't resolve it quickly, bail out of port trading.
                if insufficient_haggle_loops >= 2:
                    _set_trade_failure_reason("insufficient_credits")
                    logger.warning(
                        "Haggle stuck (insufficient credits). Aborting port trade. default=%s credits=%s",
                        default_offer,
                        credits_available,
                    )
                    # At "Your offer [X] ?" many servers only accept a number.
                    # Sending 0 is a safe, numeric abort that exits the negotiation on most TW variants.
                    await bot.session.send("0\r")
                    pending_trade = False
                    await asyncio.sleep(0.7)
                    continue

            too_low_phrase = any(
                phrase in screen_lower
                for phrase in (
                    "offer is too low",
                    "that's too low",
                    "too low",
                    "insulting offer",
                )
            )
            if too_low_phrase and hasattr(bot, "note_trade_telemetry"):
                bot.note_trade_telemetry("haggle_too_low", 1)

            too_high_phrase = any(
                phrase in screen_lower
                for phrase in (
                    "offer is too high",
                    "that's too high",
                    "too high",
                )
            )
            if too_high_phrase and hasattr(bot, "note_trade_telemetry"):
                bot.note_trade_telemetry("haggle_too_high", 1)

            # Negotiate modestly when possible. If we can't determine the side
            # (buy vs sell), or credits are unknown, fall back to accepting.
            if default_offer is not None and default_offer > 0 and last_trade_is_buy is not None:
                credits_now = credits_available
                if credits_now is None:
                    if hasattr(bot, "note_trade_telemetry"):
                        bot.note_trade_telemetry("haggle_accept", 1)
                    await bot.session.send("\r")
                    await asyncio.sleep(0.5)
                    continue

                policy = str(getattr(bot, "strategy_mode", None) or "balanced")
                strategy_id = str(
                    getattr(bot, "strategy_id", None)
                    or getattr(getattr(bot, "strategy", None), "name", None)
                    or "unknown"
                )

                # Profile by strategy/mode. This is intentionally conservative:
                # we optimize for realized credits/turn and loop safety first.
                profile_by_strategy_mode = {
                    "profitable_pairs:aggressive": {"enabled": True, "buy_discount": 0.06, "sell_markup": 0.10, "step": 0.02, "max_attempts": 2},
                    "opportunistic:aggressive": {"enabled": True, "buy_discount": 0.04, "sell_markup": 0.08, "step": 0.015, "max_attempts": 2},
                    "ai_strategy:aggressive": {"enabled": True, "buy_discount": 0.05, "sell_markup": 0.09, "step": 0.02, "max_attempts": 2},
                    "profitable_pairs:balanced": {"enabled": True, "buy_discount": 0.02, "sell_markup": 0.03, "step": 0.01, "max_attempts": 1},
                    "opportunistic:balanced": {"enabled": False, "buy_discount": 0.0, "sell_markup": 0.0, "step": 0.0, "max_attempts": 0},
                    "ai_strategy:balanced": {"enabled": False, "buy_discount": 0.0, "sell_markup": 0.0, "step": 0.0, "max_attempts": 0},
                    "profitable_pairs:conservative": {"enabled": False, "buy_discount": 0.0, "sell_markup": 0.0, "step": 0.0, "max_attempts": 0},
                    "opportunistic:conservative": {"enabled": False, "buy_discount": 0.0, "sell_markup": 0.0, "step": 0.0, "max_attempts": 0},
                    "ai_strategy:conservative": {"enabled": False, "buy_discount": 0.0, "sell_markup": 0.0, "step": 0.0, "max_attempts": 0},
                }
                base = profile_by_strategy_mode.get(
                    f"{strategy_id}:{policy}",
                    {"enabled": policy == "aggressive", "buy_discount": 0.05, "sell_markup": 0.08, "step": 0.02, "max_attempts": 2},
                )
                enabled = bool(base["enabled"])
                buy_discount = float(base["buy_discount"])
                sell_markup = float(base["sell_markup"])
                step = float(base["step"])
                max_attempts = int(base["max_attempts"])

                haggle_accept = int(getattr(bot, "haggle_accept", 0) or 0)
                haggle_counter = int(getattr(bot, "haggle_counter", 0) or 0)
                haggle_too_high = int(getattr(bot, "haggle_too_high", 0) or 0)
                haggle_too_low = int(getattr(bot, "haggle_too_low", 0) or 0)
                offers_total = haggle_accept + haggle_counter + haggle_too_high + haggle_too_low
                too_high_rate = (float(haggle_too_high) / float(offers_total)) if offers_total > 0 else 0.0
                too_low_rate = (float(haggle_too_low) / float(offers_total)) if offers_total > 0 else 0.0

                # Auto-de-risk when "too high" starts to climb.
                if offers_total >= 30 and too_high_rate >= 0.05:
                    enabled = False
                elif offers_total >= 30 and too_high_rate >= 0.02:
                    buy_discount *= 0.5
                    sell_markup *= 0.5
                    max_attempts = min(max_attempts, 1)

                # If we are repeatedly too low, move closer to default prices.
                if offers_total >= 30 and too_low_rate >= 0.03:
                    buy_discount *= 0.5
                    sell_markup *= 0.5
                    step = max(step, 0.02)

                # Many TW2002 servers treat bracketed offer as non-negotiable.
                if not enabled or max_attempts <= 0:
                    if hasattr(bot, "note_trade_telemetry"):
                        bot.note_trade_telemetry("haggle_accept", 1)
                    await bot.session.send("\r")
                    await asyncio.sleep(0.5)
                    continue

                # Reset negotiation state if the prompt's default changed (new deal).
                if last_default_offer is None or default_offer != last_default_offer:
                    haggle_attempts = 0
                    last_offer_sent = None
                    last_default_offer = default_offer

                if last_trade_is_buy:
                    # Buying from port. Start below the default, then step up.
                    max_offer = min(default_offer, credits_now)
                    if haggle_attempts == 0 or last_offer_sent is None:
                        offer = int(round(default_offer * (1.0 - buy_discount)))
                    else:
                        offer = int(round(last_offer_sent + max(1, default_offer * step)))
                    offer = max(1, min(max_offer, offer))

                    if haggle_attempts >= max_attempts or offer >= max_offer:
                        if hasattr(bot, "note_trade_telemetry"):
                            bot.note_trade_telemetry("haggle_accept", 1)
                        await bot.session.send("\r")
                    else:
                        haggle_attempts += 1
                        last_offer_sent = offer
                        if hasattr(bot, "note_trade_telemetry"):
                            bot.note_trade_telemetry("haggle_counter", 1)
                        logger.debug(
                            "haggle_buy: strategy=%s policy=%s attempt=%s default=%s offer=%s credits=%s",
                            strategy_id,
                            policy,
                            haggle_attempts,
                            default_offer,
                            offer,
                            credits_now,
                        )
                        await bot.session.send(f"{offer}\r")

                    await asyncio.sleep(0.5)
                    continue

                # Selling to port. Ask above the default, then step down.
                min_offer = default_offer
                cap = int(round(default_offer * (1.0 + sell_markup)))
                if haggle_attempts == 0 or last_offer_sent is None:
                    offer = cap
                else:
                    offer = int(round(last_offer_sent - max(1, default_offer * step)))
                offer = max(min_offer, offer)

                if haggle_attempts >= max_attempts or offer <= min_offer:
                    if hasattr(bot, "note_trade_telemetry"):
                        bot.note_trade_telemetry("haggle_accept", 1)
                    await bot.session.send("\r")
                else:
                    haggle_attempts += 1
                    last_offer_sent = offer
                    if hasattr(bot, "note_trade_telemetry"):
                        bot.note_trade_telemetry("haggle_counter", 1)
                    logger.debug(
                        "haggle_sell: strategy=%s policy=%s attempt=%s default=%s offer=%s",
                        strategy_id,
                        policy,
                        haggle_attempts,
                        default_offer,
                        offer,
                    )
                    await bot.session.send(f"{offer}\r")

                await asyncio.sleep(0.5)
                continue

            # Default: accept the server's proposed offer/price.
            if hasattr(bot, "note_trade_telemetry"):
                bot.note_trade_telemetry("haggle_accept", 1)
            await bot.session.send("\r")
            await asyncio.sleep(0.5)
            continue

        # Record a per-unit price observation when the port states the total.
        # Examples:
        # - "We'll sell them for 377 credits."
        # - "We'll buy them for 377 credits."
        if pending_trade:
            m_total = re.search(r"(?i)we'll\s+(sell|buy)\s+them\s+for\s+([\d,]+)\s+credits", screen)
            if m_total:
                trade_interaction_seen = True
                side = m_total.group(1).lower()
                try:
                    total = int(m_total.group(2).replace(",", ""))
                except Exception:
                    total = 0

                qty = last_trade_qty or last_requested_qty or 0
                if qty > 0 and total > 0 and last_trade_commodity:
                    unit = max(1, int(round(total / qty)))
                    _record_cargo_value_hint(bot, last_trade_commodity, unit, side=side)
                    # "sell" here means port sells to us -> we bought -> store as port_sells_price.
                    try:
                        if hasattr(bot, "sector_knowledge") and bot.sector_knowledge and bot.current_sector:
                            if side == "sell":
                                bot.sector_knowledge.record_port_price(
                                    bot.current_sector,
                                    last_trade_commodity,
                                    port_sells_price=unit,
                                )
                            elif side == "buy":
                                bot.sector_knowledge.record_port_price(
                                    bot.current_sector,
                                    last_trade_commodity,
                                    port_buys_price=unit,
                                )
                    except Exception:
                        pass

        # Y/N acceptability check during trade
        if "(y/n)" in last_lines or "[y/n]" in last_lines:
            if pending_trade:
                await bot.session.send("Y")
                pending_trade = False  # Trade for this commodity is done
            else:
                await bot.session.send("N")
            await asyncio.sleep(0.3)
            continue

        # StarDock hardware buy prompt (special ports sometimes route here).
        # End-state behavior: do not get stuck in this UI when attempting a port trade.
        if "which item do you wish to buy" in last_lines and "(a,b,c,q" in last_lines:
            logger.info("Stardock buy menu encountered during port trade; exiting with Q")
            await bot.session.send("Q\r")
            pending_trade = False
            await asyncio.sleep(0.5)
            continue

        # Pause/press key (transaction complete messages, etc.)
        if "[pause]" in last_lines or "press" in last_lines:
            await bot.session.send(" ")
            await asyncio.sleep(0.3)
            continue

        # Port menu with [Q] = exit option
        if "[q]" in last_lines:
            await bot.session.send("Q")
            await asyncio.sleep(0.3)
            break

        # Nothing recognized, wait a bit
        await asyncio.sleep(0.3)

    # Make sure we're out of the port and at a safe state
    await bot.recover()

    # After port transactions, the sector command prompt doesn't include credits/cargo.
    # Force an info refresh so profit/cargo accounting stays accurate.
    try:
        if getattr(bot, "session", None):
            before = bot.session.screen_change_seq()
            await bot.session.send("i")
            await bot.session.wait_for_update(timeout_ms=2500)
            changed = await bot.session.wait_for_screen_change(timeout_ms=1200, since=before)
            if changed:
                await bot.session.wait_for_update(timeout_ms=800)
    except Exception:
        pass

    # Get updated state
    new_state = await bot.orient()
    new_credits = new_state.credits or 0

    credit_change = new_credits - initial_credits
    resolved_qty = int(last_trade_qty or 0)
    if resolved_qty <= 0:
        resolved_qty = int(last_requested_qty or 0)
    resolved_is_buy = last_trade_is_buy
    if resolved_is_buy is None and trade_action in ("buy", "sell"):
        resolved_is_buy = trade_action == "buy"
    resolved_commodity = commodity or last_trade_commodity
    effective_trade = _is_effective_trade_change(
        credit_change=int(credit_change),
        trade_action=trade_action,
        is_buy=resolved_is_buy,
    )
    trade_success = _should_count_trade_completion(
        trade_interaction_seen=bool(trade_interaction_seen),
        credit_change=int(credit_change),
        trade_action=trade_action,
        is_buy=resolved_is_buy,
    )
    if trade_success:
        trade_failure_reason = None
    if resolved_qty <= 0 and effective_trade:
        resolved_qty = _infer_qty_from_credit_change(
            commodity_name=resolved_commodity,
            is_buy_side=resolved_is_buy,
            credit_delta=int(credit_change),
            sector_hint=(int(getattr(new_state, "sector", 0) or 0) or int(start_sector or 0)),
        )
    if trade_success and hasattr(bot, "note_trade_telemetry"):
        bot.note_trade_telemetry("trades_executed", 1)
        bot.note_trade_telemetry("trade_successes", 1)
    if trade_interaction_seen and resolved_qty > 0 and effective_trade:
        _record_cargo_ledger_trade(bot, resolved_commodity, resolved_is_buy, resolved_qty)
    if hasattr(bot, "note_trade_telemetry") and attempted_trade:
        bot.note_trade_telemetry("trade_attempts", 1)
    if attempted_trade and not trade_success:
        if not trade_failure_reason:
            if not trade_interaction_seen:
                _set_trade_failure_reason("no_interaction")
            elif int(credit_change) == 0:
                _set_trade_failure_reason("wrong_side")
            else:
                _set_trade_failure_reason("other")
        if hasattr(bot, "note_trade_telemetry"):
            bot.note_trade_telemetry(f"trade_fail_{trade_failure_reason or 'other'}", 1)
    if hasattr(bot, "note_trade_outcome"):
        with contextlib.suppress(Exception):
            side = "unknown"
            if resolved_is_buy is True:
                side = "buy"
            elif resolved_is_buy is False:
                side = "sell"
            elif trade_action in ("buy", "sell"):
                side = str(trade_action)
            bot.note_trade_outcome(
                sector=(int(getattr(new_state, "sector", 0) or 0) or int(start_sector or 0)),
                commodity=str(resolved_commodity or commodity or "all").strip().lower() or "all",
                side=side,
                success=bool(trade_success),
                credit_change=int(credit_change),
                failure_reason=str(trade_failure_reason or ""),
                pair_signature=pair_signature,
            )
    _publish_trade_meta(
        success=bool(trade_success),
        attempted=bool(attempted_trade),
        credit_change=int(credit_change),
        sector=(int(getattr(new_state, "sector", 0) or 0) or int(start_sector or 0)),
        resolved_commodity=resolved_commodity,
        resolved_is_buy=resolved_is_buy,
    )

    # Track local zero-change trade loops so guard mode can reroute away from bad ports.
    with contextlib.suppress(Exception):
        sig_sector = int(getattr(new_state, "sector", 0) or getattr(bot, "current_sector", 0) or 0)
        sig_commodity = str(resolved_commodity or "")
        if resolved_is_buy is True:
            sig_action = "buy"
        elif resolved_is_buy is False:
            sig_action = "sell"
        else:
            sig_action = str(trade_action or "")
        sig = (sig_sector, sig_commodity, sig_action)
        zero_map = getattr(bot, "_zero_trade_streak", None)
        if not isinstance(zero_map, dict):
            zero_map = {}
            bot._zero_trade_streak = zero_map
        if attempted_trade:
            prev = int(zero_map.get(sig, 0) or 0)
            zero_map[sig] = 0 if effective_trade else max(0, prev + 1)
            bot._last_trade_signature = sig
            bot._last_trade_credit_change = int(credit_change)

    logger.info(
        "Trade complete: %+d credits (was %d, now %d)",
        credit_change,
        initial_credits,
        new_credits,
    )
    with contextlib.suppress(Exception):
        # Successful trades imply current market intel is live.
        if int(credit_change) != 0:
            bot._port_mismatch_count = 0
            bot._port_mismatch_sectors = set()
    return credit_change


async def warp_to_sector(bot, target: int) -> bool:
    """Warp to an adjacent sector.

    Sends the sector number at the command prompt. In TW2002, typing a sector
    number at the command prompt warps to that sector if it's adjacent.

    Args:
        bot: TradingBot instance
        target: Destination sector number

    Returns:
        True if successfully reached target sector
    """
    hop_start = time.monotonic()

    def _note_hop(success: bool, reason: str | None = None) -> None:
        hook = getattr(bot, "note_warp_hop", None)
        if callable(hook):
            with contextlib.suppress(Exception):
                hook(
                    success=success,
                    latency_ms=int(max(0.0, (time.monotonic() - hop_start) * 1000.0)),
                    reason=reason,
                )

    try:
        bot.loop_detection.reset()
        from bbsbot.games.tw2002 import orientation

        # Preflight: only issue warp keys from a stable command prompt.
        quick_state = await orientation.where_am_i(bot, timeout_ms=100)
        if quick_state.context not in ("sector_command", "citadel_command"):
            logger.warning(
                "warp_preflight_recover: context=%s prompt_id=%s target=%s",
                quick_state.context,
                quick_state.prompt_id,
                target,
            )
            await bot.recover()
            quick_state = await orientation.where_am_i(bot, timeout_ms=120)
            if quick_state.context not in ("sector_command", "citadel_command"):
                _note_hop(False, "preflight_not_safe")
                return False

        await bot.session.send(f"{target}\r")
        await asyncio.sleep(1.5)

        # Handle intermediate screens (autopilot, pause, etc.)
        for _ in range(5):
            await bot.session.wait_for_update(timeout_ms=1000)
            screen = bot.session.snapshot().get("screen", "").lower()

            # Already at command prompt with target sector
            if f"[{target}]" in screen and "command" in screen:
                break

            # Autopilot confirmation
            if ("autopilot" in screen or "engage" in screen) and ("(y/n" in screen or "[y]" in screen):
                # Prefer express mode to avoid repeated "Stop in this sector" prompts.
                await bot.session.send("E")
                await asyncio.sleep(1.0)
                continue

            # Autopilot route checkpoint prompt.
            if "stop in this sector" in screen and "(y,n" in screen:
                # Prefer express mode to avoid per-hop stop prompts and navpoint/menu drift.
                await bot.session.send("E" if "(y,n,e" in screen else "N")
                await asyncio.sleep(0.6)
                continue

            # During non-adjacent routing the game may print progress screens.
            if "computing shortest path" in screen or "auto warping to sector" in screen:
                await asyncio.sleep(0.3)
                continue

            # If an accidental quit confirmation appears, reject it and continue navigation.
            if "confirmed? (y/n)" in screen and "<quit>" in screen:
                await bot.session.send("N")
                await asyncio.sleep(0.3)
                continue

            # Pause/press key
            if "[pause]" in screen or "press" in screen:
                await bot.session.send(" ")
                await asyncio.sleep(0.3)
                continue

            await asyncio.sleep(0.3)

        state = await bot.orient()
        if state.sector == target:
            _note_hop(True, "ok")
            return True

        # Orientation can occasionally read a stale sector immediately after warp.
        # Re-check using quick prompt detection before declaring failure.
        for _ in range(2):
            await asyncio.sleep(0.35)
            quick = await orientation.where_am_i(bot)
            if quick.context == "sector_command" and quick.sector == target:
                logger.debug("Warp settled after delayed recheck: target=%d", target)
                _note_hop(True, "settled_recheck")
                return True

        logger.warning("Warp failed: wanted %d, at %s", target, state.sector)
        _note_hop(False, "target_mismatch")
        return False
    except Exception as exc:
        _note_hop(False, f"exception_{type(exc).__name__.lower()}")
        raise


async def warp_along_path(bot, path: list[int]) -> bool:
    """Navigate through a multi-hop path.

    Warps through each sector in the path sequentially. The first entry
    in the path is the current sector and is skipped.

    Args:
        bot: TradingBot instance
        path: List of sector IDs [current, hop1, hop2, ..., destination]

    Returns:
        True if successfully reached the final destination
    """
    if len(path) < 2:
        return True  # Already at destination

    for i, sector in enumerate(path[1:], 1):
        print(f"    Hop {i}/{len(path) - 1}: -> {sector}")
        success = await warp_to_sector(bot, sector)
        if not success:
            logger.warning("Path navigation failed at hop %d (sector %d)", i, sector)
            return False

    return True
