"""Core orientation workflow - safety, context gathering, and navigation."""

from __future__ import annotations

import asyncio
from time import time
from typing import TYPE_CHECKING

from .detection import detect_context, SAFE_CONTEXTS
from .models import GameState, OrientationError
from .parsing import parse_display_screen, parse_sector_display

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
    # Fast check: if screen buffer already has content, do a quick TCP probe
    # then return. The probe ensures dead connections are detected early instead
    # of returning stale buffer data.
    if hasattr(bot.session, 'get_screen'):
        screen = bot.session.get_screen()
        if screen.strip():
            # TCP health probe: quick non-blocking read to verify connection is alive
            try:
                await bot.session.read(timeout_ms=10, max_bytes=1024)
            except ConnectionError:
                raise  # Dead connection - propagate immediately
            except Exception:
                pass  # Timeout is fine - connection is alive
            return screen

    last_screen = ""
    last_change_time = time()
    start_time = time()

    while True:
        elapsed_ms = (time() - start_time) * 1000
        if elapsed_ms > max_wait_ms:
            break

        try:
            result = await bot.session.read(timeout_ms=read_interval_ms, max_bytes=8192)
            screen = result.get("screen", "")
        except Exception:
            screen = last_screen

        if screen != last_screen:
            last_screen = screen
            last_change_time = time()
        else:
            # Screen unchanged - check if stable long enough
            stable_ms = (time() - last_change_time) * 1000
            if stable_ms >= stability_ms and last_screen.strip():
                break

        # Only sleep between polls if screen is still changing
        # (avoid wasting 500ms when screen is already stable but empty)
        await asyncio.sleep(0.05)

    return last_screen


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
    if hasattr(bot, 'session') and hasattr(bot.session, 'is_connected'):
        if not bot.session.is_connected():
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
            if consecutive_blank >= 3 and hasattr(bot, 'session') and hasattr(bot.session, 'is_connected'):
                if not bot.session.is_connected():
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
            print(f"  [Orient] On planet citadel, pressing Q to return to space...")
            await bot.session.send("Q")
            await asyncio.sleep(0.2)
            continue

        if context == "pause":
            print(f"  [Orient] Dismissing pause screen...")
            await bot.session.send(" ")
            await asyncio.sleep(0.8)  # Longer wait for screen to update (was 0.15s)
            continue

        if context in ("menu", "port_menu"):
            # CRITICAL FIX: If we have a stored game letter, ALWAYS try to re-enter game first
            # This handles the case where screen buffer doesn't show full menu text
            if hasattr(bot, 'last_game_letter') and bot.last_game_letter:
                # Track menu re-entries to detect if bot is being ejected
                bot.menu_reentry_count += 1
                bot.last_menu_reentry_time = time()

                if bot.menu_reentry_count > bot.max_menu_reentries:
                    raise OrientationError(
                        f"Returned to menu {bot.menu_reentry_count} times - "
                        f"bot appears to be ejected from game. Requires restart.",
                        screen=screen,
                        attempts=attempt + 1,
                    )

                # Try to re-enter the game using stored game letter
                print(f"  [Orient] At menu (re-entry #{bot.menu_reentry_count}), "
                      f"selecting game {bot.last_game_letter}")
                await bot.session.send(bot.last_game_letter + "\r")
                await asyncio.sleep(1.0)
                continue

            # No game letter stored - check if this is corporate listings
            elif context == "corporate_listings":
                # Corporate Listings menu - send Q to quit
                print(f"  [Orient] At Corporate Listings menu, sending Q to exit...")
                await bot.session.send("Q")
                await asyncio.sleep(0.3)
                continue

            # Generic menu without game letter - try Q to exit
            else:
                print(f"  [Orient] In {context}, sending Q to back out...")
                await bot.session.send("Q")
                await asyncio.sleep(0.2)
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

    # If no kv_data provided, try to get fresh semantic data from current screen
    if kv_data is None:
        from bbsbot.games.tw2002.io import wait_and_respond
        try:
            # Quick read to get semantic extraction without changing screen
            result = await bot.session.read(timeout_ms=10, max_bytes=1024)
            kv_data = result.get("kv_data", {})
            if kv_data.get('credits'):
                print(f"  [Orient] Extracted semantic data: credits={kv_data.get('credits')}")
            else:
                print(f"  [Orient] Extracted semantic data from current screen")
        except Exception:
            kv_data = {}

    # Parse sector display (warps, port, etc.)
    sector_info = parse_sector_display(screen)
    state.sector = sector_info.get('sector')
    state.warps = sector_info.get('warps', [])
    state.has_port = sector_info.get('has_port', False)
    state.port_class = sector_info.get('port_class')
    state.has_planet = sector_info.get('has_planet', False)
    state.planet_names = sector_info.get('planet_names', [])
    state.traders_present = sector_info.get('traders_present', [])
    state.hostile_fighters = sector_info.get('hostile_fighters', 0)

    # Send 'D' for full display
    print(f"  [Orient] Sending D for full status...")
    await bot.session.send("D")
    await asyncio.sleep(0.1)

    # Read display output
    # Use longer timeout for heavily loaded servers (match login timeout)
    from bbsbot.games.tw2002.io import wait_and_respond
    try:
        _, _, display_screen, display_kv = await wait_and_respond(
            bot,
            timeout_ms=60000,  # 60 seconds for heavily loaded servers
            # Ignore loop detection for D command - it's normal to see sector_command prompt again
            ignore_loop_for={"prompt.pause_simple", "prompt.pause_space_or_enter", "prompt.sector_command"},
        )

        # Parse display output
        display_info = parse_display_screen(display_screen)
        if not display_info.get('credits'):
            print(f"  [Orient] D command parsing found no credits (display_screen might be a prompt)")

        # Multi-source fallback: Use display parse first, then kv_data, then initial kv_data
        # This provides 3 layers of fallback for critical game state
        def get_with_fallback(key: str):
            """Get value with fallback chain: display_info -> display_kv -> kv_data"""
            value = display_info.get(key)
            if value is not None:
                return value
            if display_kv and key in display_kv:
                return display_kv.get(key)
            if kv_data and key in kv_data:
                return kv_data.get(key)
            return None

        # Credits: Always prefer semantic data if display parsing fails
        # The D command often returns a prompt instead of actual display data
        state.credits = get_with_fallback('credits')
        # If we got 0 or None, try semantic data from kv_data
        if (state.credits is None or state.credits == 0) and kv_data and 'credits' in kv_data:
            semantic_credits = kv_data.get('credits')
            if semantic_credits is not None and semantic_credits > 0:
                state.credits = semantic_credits
                print(f"  [Orient] Using semantic credits (fallback from 0): {state.credits}")
        # Final fallback: bot.last_semantic_data (populated by io callbacks)
        if (state.credits is None or state.credits == 0):
            bot_semantic = getattr(bot, 'last_semantic_data', {})
            if bot_semantic.get('credits') and bot_semantic['credits'] > 0:
                state.credits = bot_semantic['credits']
                print(f"  [Orient] Using bot.last_semantic_data credits: {state.credits}")

        state.turns_left = get_with_fallback('turns_left')

        state.fighters = get_with_fallback('fighters')
        if (state.fighters is None or state.fighters == 0) and kv_data and kv_data.get('fighters'):
            state.fighters = kv_data.get('fighters')

        state.shields = get_with_fallback('shields')
        if (state.shields is None or state.shields == 0) and kv_data and kv_data.get('shields'):
            state.shields = kv_data.get('shields')
        state.holds_total = get_with_fallback('holds_total')
        state.holds_free = get_with_fallback('holds_free')
        state.ship_type = get_with_fallback('ship_type')
        state.player_name = get_with_fallback('player_name')
        state.alignment = get_with_fallback('alignment')
        state.experience = get_with_fallback('experience')
        state.corp_id = get_with_fallback('corp_id')

        # Sector from display if not already set
        if state.sector is None:
            state.sector = get_with_fallback('sector')

        # Update raw screen with full display
        state.raw_screen = display_screen

        # Debug: Log which source provided credits
        if state.credits is not None:
            if display_info.get('credits'):
                print(f"  [Orient] Credits from D command: {state.credits}")
            elif display_kv and display_kv.get('credits'):
                print(f"  [Orient] Credits from D semantic: {state.credits}")
            elif kv_data and kv_data.get('credits'):
                print(f"  [Orient] Credits from sector semantic: {state.credits}")

    except Exception as e:
        print(f"  [Orient] Warning: Display command failed: {e}")
        # Even if D command fails, try to use semantic data
        if kv_data:
            state.credits = kv_data.get('credits')
            state.turns_left = kv_data.get('turns_left')
            state.fighters = kv_data.get('fighters')
            state.shields = kv_data.get('shields')
            if state.credits is not None:
                print(f"  [Orient] Using fallback semantic credits: {state.credits}")

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
