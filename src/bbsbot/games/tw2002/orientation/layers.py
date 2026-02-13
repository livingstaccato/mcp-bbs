# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Core orientation workflow - safety, context gathering, and navigation."""

from __future__ import annotations

import asyncio
from time import time
from typing import TYPE_CHECKING

from .detection import detect_context
from .models import GameState, OrientationError
from .parsing import parse_sector_display

if TYPE_CHECKING:
    from bbsbot.games.tw2002.bot import TradingBot

    from .knowledge import SectorKnowledge


async def _wait_for_screen_stability(
    bot: TradingBot,
    stability_ms: int = 100,
    max_wait_ms: int = 2000,
    read_interval_ms: int = 500,  # CRITICAL FIX: Changed from 100 -> 500 to prevent tight polling loops
) -> str:
    """Wait until screen content stops changing (handles baud rate rendering).

    At low baud rates, characters arrive one at a time. This function reads
    repeatedly until the screen content hasn't changed for `stability_ms`.

    Args:
        bot: TradingBot instance
        stability_ms: How long screen must be unchanged to be considered stable
        max_wait_ms: Maximum total time to wait
        read_interval_ms: How often to poll the screen (default 500ms to avoid tight loops)

    Returns:
        Stable screen content
    """
    start_mono = asyncio.get_running_loop().time()
    stability_s = max(0.0, stability_ms / 1000.0)
    max_wait_s = max(0.0, max_wait_ms / 1000.0)

    # Event-driven: wait for the screen hash to stop changing.
    while (asyncio.get_running_loop().time() - start_mono) < max_wait_s:
        screen = bot.session.snapshot().get("screen", "")
        if screen.strip() and bot.session.is_idle(threshold_s=stability_s):
            return screen
        remaining_ms = int(max(1, (max_wait_s - (asyncio.get_running_loop().time() - start_mono)) * 1000))
        await bot.session.wait_for_update(timeout_ms=min(read_interval_ms, remaining_ms))

    return bot.session.snapshot().get("screen", "")


def _set_orient_progress(bot: TradingBot, step: int, max_steps: int, phase: str) -> None:
    """Update orient progress on bot for dashboard visibility."""
    bot._orient_step = step
    bot._orient_max = max_steps
    bot._orient_phase = phase


async def _reach_safe_state(
    bot: TradingBot,
    max_attempts: int = 10,
    stability_ms: int = 100,
) -> tuple[str, str, str]:
    """Try to reach a safe state using gentle escapes.

    Uses screen stability detection to handle baud rate rendering delays.

    Returns:
        Tuple of (context, prompt_id, screen)

    Raises:
        OrientationError if unable to reach safe state
        ConnectionError if session is disconnected
    """
    gentle_keys = [" ", "\r", " ", "\r", "Q", " ", "\r", "Q", " ", "\r"]

    # Pre-check: is the session even connected?
    if hasattr(bot, "session") and hasattr(bot.session, "is_connected") and not bot.session.is_connected():
        raise ConnectionError("Session disconnected - cannot orient")

    last_screen = ""
    consecutive_blank = 0

    for attempt in range(max_attempts):
        _set_orient_progress(bot, attempt + 1, max_attempts, "safe_state")

        # Wait for screen to stabilize (handles baud rate rendering)
        try:
            screen = await _wait_for_screen_stability(
                bot,
                stability_ms=stability_ms,
                max_wait_ms=2000,
            )
            if screen.strip():
                last_screen = screen
        except Exception:
            screen = last_screen

        # Blank screen handling: progressive wake-up keys
        if not screen.strip():
            consecutive_blank += 1
            _set_orient_progress(bot, attempt + 1, max_attempts, "blank_wake")
            # After 3 blank screens, check if connection is dead
            if (
                consecutive_blank >= 3
                and hasattr(bot, "session")
                and hasattr(bot.session, "is_connected")
                and not bot.session.is_connected()
            ):
                raise ConnectionError("Session disconnected during orientation (blank screen)")
            # SAFE keys only - no Enter/CR which could confirm trades or trigger warps
            # NUL first: true no-op but proves TCP socket is alive
            wake_keys = ["\x00", " ", "\x1b", "?", " ", "\x7f"]
            if attempt < len(wake_keys):
                key = wake_keys[attempt]
                print(f"  [Orient] Blank screen, wake key {repr(key)} ({attempt + 1}/{max_attempts})...")
                await bot.session.send(key)
                await asyncio.sleep(0.2)
                continue
        else:
            consecutive_blank = 0

        # Check if we're in a safe state using our context detection
        context = detect_context(screen)

        if context in ("sector_command", "citadel_command"):
            _set_orient_progress(bot, 0, 0, "")
            print(f"  [Orient] Safe state reached: {context}")
            return context, "", screen

        if context == "planet_command":
            print("  [Orient] On planet citadel, pressing Q to return to space...")
            await bot.session.send("Q")
            await asyncio.sleep(0.2)
            continue

        if context == "pause":
            print("  [Orient] Dismissing pause screen...")
            await bot.session.send(" ")
            await asyncio.sleep(0.8)  # Longer wait for screen to update (was 0.15s)
            continue

        if context == "port_menu":
            # Port menu is inside the game. Re-sending the game letter here can
            # trigger unintended actions; always back out with Q.
            print("  [Orient] At port menu, sending Q to return to sector command...")
            await bot.session.send("Q")
            await asyncio.sleep(0.4)
            continue

        if context == "menu":
            # True game-selection menu: if we have a stored game letter, re-enter.
            if hasattr(bot, "last_game_letter") and bot.last_game_letter:
                bot.menu_reentry_count += 1
                bot.last_menu_reentry_time = time()

                if bot.menu_reentry_count > bot.max_menu_reentries:
                    raise OrientationError(
                        f"Returned to menu {bot.menu_reentry_count} times - "
                        f"bot appears to be ejected from game. Requires restart.",
                        screen=screen,
                        attempts=attempt + 1,
                    )

                print(f"  [Orient] At menu (re-entry #{bot.menu_reentry_count}), selecting game {bot.last_game_letter}")
                await bot.session.send(bot.last_game_letter + "\r")
                await asyncio.sleep(1.0)
                continue

            print("  [Orient] At menu without stored game letter, sending Q to back out...")
            await bot.session.send("Q")
            await asyncio.sleep(0.2)
            continue

        if context == "corporate_listings":
            print("  [Orient] At Corporate Listings menu, sending Q to exit...")
            await bot.session.send("Q")
            await asyncio.sleep(0.3)
            continue

        # Unknown or unrecognized - try gentle escape
        if attempt < len(gentle_keys):
            key = gentle_keys[attempt]
            key_name = repr(key).replace("'", "")
            print(f"  [Orient] State '{context}', trying {key_name} ({attempt + 1}/{max_attempts})...")
            await bot.session.send(key)
            await asyncio.sleep(0.15)

    _set_orient_progress(bot, 0, 0, "failed")
    raise OrientationError(
        f"Failed to reach safe state after {max_attempts} attempts",
        screen=last_screen,
        attempts=max_attempts,
    )


async def _gather_state(
    bot: TradingBot,
    context: str,
    screen: str,
    prompt_id: str,
    kv_data: dict | None = None,
) -> GameState:
    """Gather comprehensive game state via Display command.

    Uses multiple data sources with fallbacks:
    1. Display command (D) screen parsing
    2. Semantic extraction (kv_data)
    3. Sector display parsing

    Args:
        bot: TradingBot instance
        context: Current context (sector_command, etc.)
        screen: Current screen content
        prompt_id: Current prompt ID
        kv_data: Optional semantic/extracted data from current screen

    Returns:
        Populated GameState
    """
    # Start with state from current screen
    state = GameState(
        context=context,
        raw_screen=screen,
        prompt_id=prompt_id,
    )

    # Best-effort cargo snapshot (this is primarily populated when we pass through
    # port/transaction screens; keep it in GameState so strategies can sell cargo).
    bot_semantic_initial = getattr(bot, "last_semantic_data", {}) or {}
    try:
        state.cargo_fuel_ore = int(bot_semantic_initial.get("cargo_fuel_ore") or 0)
        state.cargo_organics = int(bot_semantic_initial.get("cargo_organics") or 0)
        state.cargo_equipment = int(bot_semantic_initial.get("cargo_equipment") or 0)
    except Exception:
        # Keep as None/0-ish if parsing fails; strategies should treat missing as 0.
        pass

    # If no kv_data provided, try to get fresh semantic data from current screen
    if kv_data is None:
        from bbsbot.games.tw2002.io import wait_and_respond

        try:
            snap = bot.session.snapshot()
            kv_data = (snap.get("prompt_detected") or {}).get("kv_data") or {}
            if kv_data.get("credits"):
                print(f"  [Orient] Extracted semantic data: credits={kv_data.get('credits')}")
            else:
                print("  [Orient] Extracted semantic data from current screen")
        except Exception:
            kv_data = {}

    # Parse sector display (warps, port, etc.)
    sector_info = parse_sector_display(screen)
    state.sector = sector_info.get("sector")
    state.warps = sector_info.get("warps", [])
    state.has_port = sector_info.get("has_port", False)
    state.port_class = sector_info.get("port_class")
    state.has_planet = sector_info.get("has_planet", False)
    state.planet_names = sector_info.get("planet_names", [])
    state.traders_present = sector_info.get("traders_present", [])
    state.hostile_fighters = sector_info.get("hostile_fighters", 0)

    # This server's `D` is "Re-Display" (sector), not "stats". We still need an
    # early, cheap stats refresh so strategies can reason about bankroll/holds.
    #
    # Empirically, `i` prints a credits line ("You have X credits") and returns
    # to the command prompt without consuming turns.
    from bbsbot.games.tw2002.io import wait_and_respond
    from bbsbot.games.tw2002.parsing import extract_semantic_kv

    try:
        bot_semantic_before = getattr(bot, "last_semantic_data", {}) or {}
        stats_refresh_attempts = int(getattr(bot, "_stats_refresh_attempts", 0))
        last_stats_refresh_ts = float(getattr(bot, "_last_stats_refresh_ts", 0.0))

        def merged_value(key: str):
            if kv_data and key in kv_data and kv_data.get(key) is not None:
                return kv_data.get(key)
            if bot_semantic_before and key in bot_semantic_before and bot_semantic_before.get(key) is not None:
                return bot_semantic_before.get(key)
            return None

        core_keys = ("credits", "holds_total", "holds_free", "fighters", "shields")
        missing_core = [k for k in core_keys if merged_value(k) is None]
        should_refresh_stats = bool(missing_core) and stats_refresh_attempts < 4 and ((time() - last_stats_refresh_ts) >= 1.5)

        if should_refresh_stats:
            print(f"  [Orient] Refreshing stats via '/' quick-stats (missing: {', '.join(missing_core)})...")
            refresh_cmds = ["/"]
            if context == "sector_command":
                refresh_cmds.append("i\r")
            for refresh_cmd in refresh_cmds:
                await bot.session.send(refresh_cmd)
                await asyncio.sleep(0.05)
                _, _, info_screen, _ = await wait_and_respond(
                    bot,
                    timeout_ms=10000,
                    ignore_loop_for={"prompt.pause_simple", "prompt.pause_space_or_enter", "prompt.sector_command"},
                )
                # Ensure semantic updates even if the waiter's callback missed the transient line.
                bot.last_semantic_data.update(extract_semantic_kv(info_screen))
                sem_now = getattr(bot, "last_semantic_data", {}) or {}
                if all(sem_now.get(k) is not None for k in core_keys):
                    break
            bot._stats_refresh_attempts = stats_refresh_attempts + 1
            bot._last_stats_refresh_ts = time()

        # Build a best-effort snapshot from merged semantic cache.
        bot_semantic = getattr(bot, "last_semantic_data", {}) or {}

        def get_with_fallback(key: str):
            if kv_data and key in kv_data and kv_data.get(key) is not None:
                return kv_data.get(key)
            if bot_semantic and key in bot_semantic and bot_semantic.get(key) is not None:
                return bot_semantic.get(key)
            return None

        state.credits = get_with_fallback("credits")
        state.turns_left = get_with_fallback("turns_left")
        state.fighters = get_with_fallback("fighters")
        state.shields = get_with_fallback("shields")
        state.holds_total = get_with_fallback("holds_total")
        state.holds_free = get_with_fallback("holds_free")
        state.ship_type = get_with_fallback("ship_type")
        state.player_name = get_with_fallback("player_name")
        state.alignment = get_with_fallback("alignment")
        state.experience = get_with_fallback("experience")
        state.corp_id = get_with_fallback("corp_id")
        state.ship_name = get_with_fallback("ship_name")

        # Mark refresh complete once core state is present.
        if all(get_with_fallback(k) is not None for k in core_keys):
            bot._stats_refreshed = True

        # Cargo is primarily learned from port tables; default to 0 if unknown.
        try:
            state.cargo_fuel_ore = int(bot_semantic.get("cargo_fuel_ore") or 0)
            state.cargo_organics = int(bot_semantic.get("cargo_organics") or 0)
            state.cargo_equipment = int(bot_semantic.get("cargo_equipment") or 0)
        except Exception:
            pass
    except Exception as e:
        print(f"  [Orient] Warning: Stats refresh failed: {e}")

    return state


async def orient(
    bot: TradingBot,
    knowledge: SectorKnowledge | None = None,
) -> GameState:
    """Complete orientation sequence.

    1. Safety - Reach a known stable state
    2. Context - Gather comprehensive game state
    3. Navigation - Record observations for future pathfinding

    Args:
        bot: TradingBot instance
        knowledge: Optional SectorKnowledge for recording observations

    Returns:
        Complete GameState

    Raises:
        OrientationError if unable to establish safe state
    """
    t0 = time()
    _set_orient_progress(bot, 0, 10, "starting")
    print("\n[Orientation] Starting...")

    # Layer 1: Safety
    context, prompt_id, screen = await _reach_safe_state(bot)
    t1 = time()

    # Layer 2: Context
    _set_orient_progress(bot, 0, 0, "gather")
    state = await _gather_state(bot, context, screen, prompt_id)
    t2 = time()

    # Layer 3: Navigation - Record what we learned
    if knowledge and state.sector:
        knowledge.record_observation(state)

    _set_orient_progress(bot, 0, 0, "")
    total_ms = (t2 - t0) * 1000
    safe_ms = (t1 - t0) * 1000
    gather_ms = (t2 - t1) * 1000
    print(f"  [Orient] Complete: {state.summary()} [{total_ms:.0f}ms: safe={safe_ms:.0f}ms gather={gather_ms:.0f}ms]")

    return state
