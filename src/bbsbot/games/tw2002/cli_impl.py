# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Implementation helpers for the TW2002 CLI."""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
from typing import TYPE_CHECKING

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
    guard_overage: int = 0,
) -> tuple[TradeAction, dict] | None:
    """Hard trade-urgency override when the no-trade guard is active."""
    if state.context != "sector_command":
        return None

    current_sector = int(state.sector or 0)
    info = knowledge.get_sector_info(current_sector) if current_sector > 0 else None
    statuses = _derive_port_statuses(getattr(state, "port_class", None), info)
    cargo = {
        "fuel_ore": int(getattr(state, "cargo_fuel_ore", 0) or 0),
        "organics": int(getattr(state, "cargo_organics", 0) or 0),
        "equipment": int(getattr(state, "cargo_equipment", 0) or 0),
    }

    if bool(getattr(state, "has_port", False)) and current_sector > 0:
        # First priority: sell whatever we already hold into local demand.
        for commodity, qty in cargo.items():
            if qty > 0 and statuses.get(commodity) == "buying":
                return TradeAction.TRADE, {
                    "commodity": commodity,
                    "action": "sell",
                    "max_quantity": qty,
                    "urgency": "no_trade_guard",
                }

        # Second priority: buy the cheapest local commodity the port is selling.
        holds_free = max(0, int(getattr(state, "holds_free", 0) or 0))
        allow_local_buy_attempt = guard_overage <= 1
        if allow_local_buy_attempt and holds_free > 0 and int(credits_now or 0) > 0:
            sellables = [c for c in ("fuel_ore", "organics", "equipment") if statuses.get(c) == "selling"]
            if sellables:
                prices = (getattr(info, "port_prices", {}) or {}) if info else {}

                def _rank_buy(comm: str) -> tuple[int, str]:
                    quoted = (prices.get(comm) or {}).get("sell")
                    try:
                        p = int(quoted) if quoted is not None else 10**9
                    except Exception:
                        p = 10**9
                    return (p, comm)

                commodity = sorted(sellables, key=_rank_buy)[0]
                quoted = (prices.get(commodity) or {}).get("sell")
                qty = 1
                with contextlib.suppress(Exception):
                    qv = int(quoted) if quoted is not None else 0
                    if qv > 0:
                        affordable = int(credits_now // qv)
                        # If we cannot afford even one unit, do not force a local buy
                        # and fall back to movement/exploration below.
                        qty = min(holds_free, affordable) if affordable > 0 else 0
                    else:
                        # Unknown price: keep buys small until we build market intel.
                        qty = min(holds_free, 2 if int(credits_now) < 2000 else 4)
                if qty > 0:
                    return TradeAction.TRADE, {
                        "commodity": commodity,
                        "action": "buy",
                        "max_quantity": qty,
                        "urgency": "no_trade_guard",
                    }

    # Not at a usable port: force movement to nearest known port.
    if current_sector > 0:
        best_path: list[int] | None = None
        best_sector: int | None = None
        known = getattr(knowledge, "_sectors", {}) or {}
        for sector, sector_info in known.items():
            if int(sector) == current_sector:
                continue
            if not getattr(sector_info, "has_port", False):
                continue
            path = knowledge.find_path(current_sector, int(sector), max_hops=20)
            if not path or len(path) < 2:
                continue
            if best_path is None or len(path) < len(best_path):
                best_path = path
                best_sector = int(sector)
        if best_path and best_sector:
            return TradeAction.MOVE, {
                "target_sector": best_sector,
                "path": best_path,
                "urgency": "no_trade_guard",
            }

    warps = [int(w) for w in (state.warps or []) if int(w) != current_sector]
    if warps:
        target = sorted(warps)[0]
        return TradeAction.EXPLORE, {"direction": target, "urgency": "no_trade_guard"}
    return None


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
                elif isinstance(e, (TimeoutError, ConnectionError, OrientationError)):
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
                if hasattr(bot, "session") and hasattr(bot.session, "is_connected") and not bot.session.is_connected():
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
            continue

        # Successful orient - reset failure counter
        consecutive_orient_failures = 0

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
        def _compute_policy(credits_now: int | None) -> str:
            policy = getattr(config.trading, "policy", "dynamic")
            if policy and policy != "dynamic":
                return policy
            credits_val = int(credits_now or 0)
            dyn = getattr(config.trading, "dynamic_policy", None)
            try:
                conservative_under = int(getattr(dyn, "conservative_under_credits", 5000)) if dyn else 5000
                aggressive_over = int(getattr(dyn, "aggressive_over_credits", 50000)) if dyn else 50000
            except Exception:
                conservative_under = 5000
                aggressive_over = 50000
            if credits_val < conservative_under:
                return "conservative"
            if credits_val >= aggressive_over:
                return "aggressive"
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
        guard_turns = int(getattr(config.trading, "no_trade_guard_turns", 60))
        guard_min_trades = int(getattr(config.trading, "no_trade_guard_min_trades", 1))
        guard_stale_turns = int(getattr(config.trading, "no_trade_guard_stale_turns", guard_turns))
        guard_strategy = str(getattr(config.trading, "no_trade_guard_strategy", "profitable_pairs"))
        guard_mode = str(getattr(config.trading, "no_trade_guard_mode", "balanced"))
        trades_done = int(getattr(bot, "trades_executed", 0) or 0)
        turns_since_last_trade = turns_used if last_trade_turn <= 0 else max(0, turns_used - last_trade_turn)
        force_guard = (turns_used >= guard_turns and trades_done < guard_min_trades) or (
            turns_since_last_trade >= guard_stale_turns
        )

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
            with contextlib.suppress(Exception):
                bot.strategy_intent = f"RECOVERY:FORCE_{guard_strategy.upper()}"
        elif ai_policy_locked:
            # End-state AI behavior: policy is controlled by AI supervisor decisions.
            effective_policy = str(getattr(strategy, "policy", None) or "balanced")
        else:
            effective_policy = _compute_policy(getattr(state, "credits", None))

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

        if force_guard:
            forced = _choose_no_trade_guard_action(
                state=state,
                knowledge=bot.sector_knowledge,
                credits_now=int(getattr(state, "credits", 0) or 0),
                guard_overage=max(0, int(turns_since_last_trade - guard_stale_turns)),
            )
            if forced is not None:
                action, params = forced
                logger.warning(
                    "no_trade_guard_force_action: turns=%s trades=%s action=%s params=%s",
                    turns_used,
                    trades_done,
                    action.name,
                    params,
                )
                with contextlib.suppress(Exception):
                    bot.strategy_intent = f"RECOVERY:TRADE_URGENCY {action.name}"

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
        try:
            # Pause again right before acting (lets hijack take effect between planning and acting).
            await_if_hijacked2 = getattr(bot, "await_if_hijacked", None)
            if callable(await_if_hijacked2):
                await await_if_hijacked2()

            if action == TradeAction.TRADE:
                opportunity = params.get("opportunity")
                trade_action = params.get("action")  # "buy" or "sell" for pair trading
                commodity = opportunity.commodity if opportunity else params.get("commodity")

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
                    profit = await execute_port_trade(bot, commodity=None)
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
                print("  No action available, exploring randomly")
                warps = list(state.warps or [])
                if not warps and state.sector is not None:
                    known_warps = bot.sector_knowledge.get_warps(int(state.sector))
                    if known_warps:
                        warps = list(known_warps)
                if warps:
                    target = random.choice(warps)
                    print(f"  WAIT fallback move to sector {target}")
                    success = await warp_to_sector(bot, target)
                else:
                    # No actionable movement data: avoid burning a synthetic turn.
                    turns_counted = 0
                    success = False
                    print("  No warps available; attempting recovery")
                    with contextlib.suppress(Exception):
                        await bot.recover()

            elif action == TradeAction.DONE:
                print("  Strategy complete")
                break
        except Exception as e:
            print(f"  ⚠️  Action failed: {type(e).__name__}: {e}")
            success = False

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

        result = TradeResult(
            success=success,
            action=action,
            profit=profit,
            new_sector=bot.current_sector,
            turns_used=turns_counted,
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

    # Dock at port
    await bot.session.send("P")
    await asyncio.sleep(1.0)

    await bot.session.wait_for_update(timeout_ms=2000)
    screen = bot.session.snapshot().get("screen", "").lower()

    if "no port" in screen:
        await bot.recover()
        return 0

    # Start trading (T for transaction)
    await bot.session.send("T")
    await asyncio.sleep(1.5)

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
            offered_all_credits = False
            insufficient_haggle_loops = 0
            haggle_attempts = 0
            last_default_offer = None
            last_offer_sent = None

            # Find the "how many" line to identify the commodity
            prompt_line = last_line
            is_buy = " buy" in prompt_line or prompt_line.strip().startswith("how many") and " buy" in prompt_line
            is_sell = " sell" in prompt_line
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

                    # If the caller specified buy/sell, enforce it.
                    if trade_action == "buy" and not is_buy:
                        await bot.session.send("0\r")
                        pending_trade = False
                        logger.debug("Skipping target commodity due to action mismatch (wanted=buy)")
                        await asyncio.sleep(0.3)
                        continue
                    if trade_action == "sell" and not is_sell:
                        await bot.session.send("0\r")
                        pending_trade = False
                        logger.debug("Skipping target commodity due to action mismatch (wanted=sell)")
                        await asyncio.sleep(0.3)
                        continue

                    # If we're trying to sell but the port reports we have none, skip.
                    if trade_action == "sell" and "you have 0 in your holds" in screen_lower:
                        await bot.session.send("0\r")
                        pending_trade = False
                        logger.debug("Skipping sell: no cargo in holds")
                        await asyncio.sleep(0.3)
                        continue

                    if max_quantity > 0:
                        # If we are buying and credits are unknown/low, never accept a large max_quantity.
                        if is_buy and (credits_available is None or credits_available < 1000):
                            qty_str = "1"
                        else:
                            qty_str = str(max_quantity)
                    else:
                        # If we are buying and credits are unknown/low, do not accept the game's default.
                        # Default quantities frequently lead to "Your offer [X] ?" loops when broke.
                        qty_str = "1" if is_buy and (credits_available is None or credits_available < 1000) else ""
                    await bot.session.send(f"{qty_str}\r")
                    pending_trade = True
                    logger.debug("Trading %s (qty=%s)", commodity, qty_str or "max")
                else:
                    # Strict targeted trade: skip anything that's not the target to avoid
                    # buying/selling unintended commodities (and getting stuck haggling).
                    await bot.session.send("0\r")
                    pending_trade = False
                    logger.debug("Skipping non-target commodity (target=%s)", commodity)
            else:
                # Trade all: avoid buys when credits are very low; still allow sells.
                if max_quantity > 0:
                    if is_buy and (credits_available is None or credits_available < 1000):
                        await bot.session.send("1\r")
                    else:
                        await bot.session.send(f"{max_quantity}\r")
                else:
                    # If we are buying and credits are unknown/low, do not accept the default.
                    qty_str = "1" if (is_buy and (credits_available is None or credits_available < 1000)) else ""
                    await bot.session.send(f"{qty_str}\r")
                pending_trade = True

            await asyncio.sleep(0.5)
            continue

        # Capture "Agreed, N units." to compute per-unit pricing when the total appears.
        m_agreed = re.search(r"(?i)\bagreed,\s*([\d,]+)\s+units\b", last_lines)
        if m_agreed:
            with contextlib.suppress(Exception):
                last_trade_qty = int(m_agreed.group(1).replace(",", ""))

        # Price/offer negotiation - only respond if we have a pending trade
        if pending_trade and ("offer" in last_lines or "price" in last_lines or "haggl" in last_lines):
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
                side = m_total.group(1).lower()
                try:
                    total = int(m_total.group(2).replace(",", ""))
                except Exception:
                    total = 0

                qty = last_trade_qty or 0
                if qty > 0 and total > 0 and last_trade_commodity:
                    unit = max(1, int(round(total / qty)))
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
    if credit_change != 0 and hasattr(bot, "note_trade_telemetry"):
        bot.note_trade_telemetry("trades_executed", 1)
    logger.info(
        "Trade complete: %+d credits (was %d, now %d)",
        credit_change,
        initial_credits,
        new_credits,
    )
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
    bot.loop_detection.reset()

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
        if "(y/n)" in screen and ("autopilot" in screen or "engage" in screen):
            await bot.session.send("Y")
            await asyncio.sleep(1.0)
            continue

        # Pause/press key
        if "[pause]" in screen or "press" in screen:
            await bot.session.send(" ")
            await asyncio.sleep(0.3)
            continue

        await asyncio.sleep(0.3)

    state = await bot.orient()
    if state.sector == target:
        return True

    # Orientation can occasionally read a stale sector immediately after warp.
    # Re-check using quick prompt detection before declaring failure.
    from bbsbot.games.tw2002 import orientation

    for _ in range(2):
        await asyncio.sleep(0.35)
        quick = await orientation.where_am_i(bot)
        if quick.context == "sector_command" and quick.sector == target:
            logger.debug("Warp settled after delayed recheck: target=%d", target)
            return True

    logger.warning("Warp failed: wanted %d, at %s", target, state.sector)
    return False


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
