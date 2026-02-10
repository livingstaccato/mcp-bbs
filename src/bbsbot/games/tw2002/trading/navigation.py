"""Sector navigation and warping for trading operations."""

from __future__ import annotations

import asyncio
from pathlib import Path

from bbsbot.games.tw2002.io import send_input, wait_and_respond
from bbsbot.logging import get_logger

from .parsers import extract_sector_from_screen
from .validation import validate_kv_data

logger = get_logger(__name__)


async def warp_to_sector(bot, target_sector: int) -> None:
    """Warp to target sector.

    Args:
        bot: TradingBot instance
        target_sector: Destination sector number

    Raises:
        RuntimeError: On warp failures or anomalies
    """
    if bot.current_sector == target_sector:
        print(f"  Already at sector {target_sector}; skipping warp")
        return

    # Get to command menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  Got prompt: {prompt_id}")
    if prompt_id == "prompt.planet_command":
        print("  On planet surface, exiting to sector command...")
        await bot.session.send("Q")
        await asyncio.sleep(0.5)
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
        print(f"  After exit: {prompt_id}")
        if prompt_id == "prompt.planet_command":
            raise RuntimeError("still_on_planet")

    # If we're already at the warp-sector input prompt, don't send "M" again.
    pre_warp_sector = bot.current_sector
    warp_prompt_seen = False
    warp_input_type = None
    if prompt_id == "prompt.warp_sector":
        warp_prompt_seen = True
        warp_input_type = input_type
        if kv_data and "current_sector" in kv_data:
            pre_warp_sector = kv_data["current_sector"]
    else:
        # Send "M" for Move/Warp
        print(f"  Initiating warp to sector {target_sector}...")
        await bot.session.send("M")  # Single key
        await asyncio.sleep(0.3)

        # Wait for sector input prompt (validate prompt type)
        for _ in range(6):
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot,
                timeout_ms=3000,
                ignore_loop_for={"prompt.pause_simple", "prompt.pause_space_or_enter"},
            )
            print(f"  Warp prompt: {prompt_id}")
            if prompt_id == "prompt.warp_sector":
                is_valid, error_msg = validate_kv_data(kv_data, prompt_id)
                if not is_valid:
                    print(f"  ⚠️  {error_msg}")
                if kv_data and "current_sector" in kv_data:
                    pre_warp_sector = kv_data["current_sector"]
                warp_prompt_seen = True
                warp_input_type = input_type  # Save the correct input type
                break
            if prompt_id in ("prompt.pause_simple", "prompt.pause_space_or_enter") or input_type == "any_key":
                await send_input(bot, "", input_type)
                await asyncio.sleep(0.2)
                continue
            if prompt_id == "prompt.yes_no":
                screen_lower = screen.lower()
                if "autopilot" in screen_lower or "engage" in screen_lower:
                    await send_input(bot, "Y", input_type)
                else:
                    await send_input(bot, "N", input_type)
                await asyncio.sleep(0.2)
                continue
            if prompt_id == "prompt.avoid_sector_add":
                # Don't avoid sectors - we want to explore everywhere
                await send_input(bot, "N", input_type)
                await asyncio.sleep(0.2)
                continue
            if prompt_id in ("prompt.sector_command", "prompt.command_generic"):
                # Retry sending warp command if we missed it
                await bot.session.send("M")
                await asyncio.sleep(0.3)
                continue
            raise RuntimeError(f"unexpected_warp_prompt:{prompt_id}")

        if not warp_prompt_seen:
            raise RuntimeError("warp_prompt_missing")

    # Send destination sector (multi_key) - use saved input type from warp prompt
    await send_input(bot, str(target_sector), warp_input_type)

    # Wait for arrival confirmation and reach a stable prompt
    arrival_screen = ""
    for _ in range(6):
        try:
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot,
                timeout_ms=5000,
                ignore_loop_for={"prompt.pause_simple", "prompt.pause_space_or_enter"},
            )
        except TimeoutError:
            break
        print(f"  Warp status: {prompt_id}")
        arrival_screen = screen
        if prompt_id in ("prompt.pause_simple", "prompt.pause_space_or_enter") or input_type == "any_key":
            await send_input(bot, "", input_type)
            await asyncio.sleep(0.2)
            continue
        if prompt_id == "prompt.yes_no":
            screen_lower = screen.lower()
            if "autopilot" in screen_lower or "engage" in screen_lower:
                await send_input(bot, "Y", input_type)
            else:
                await send_input(bot, "N", input_type)
            await asyncio.sleep(0.2)
            continue
        if prompt_id in ("prompt.sector_command", "prompt.command_generic"):
            break

    # Post-warp anomaly checks
    post_sector = extract_sector_from_screen(arrival_screen) if arrival_screen else None
    if post_sector is None:
        quick_state = await bot.where_am_i()
        post_sector = quick_state.sector
    if post_sector is None:
        raise RuntimeError("warp_sector_unknown")
    if pre_warp_sector and post_sector == pre_warp_sector:
        raise RuntimeError("warp_no_change")
    if post_sector != target_sector:
        raise RuntimeError(f"warp_failed:{post_sector}")

    bot.current_sector = post_sector

    print(f"  ✓ Warped to sector {target_sector}")
    await asyncio.sleep(0.5)


async def navigate_path(bot, path: list[int]) -> None:
    """Navigate through a series of sectors.

    Args:
        bot: TradingBot instance
        path: List of sector IDs to traverse

    Raises:
        RuntimeError: On navigation failures
    """
    if len(path) < 2:
        return  # Already at destination or no path

    print(f"  Navigating: {' -> '.join(str(s) for s in path)}")

    # Skip first sector (current location)
    for sector in path[1:]:
        await warp_to_sector(bot, sector)


async def resolve_paths(
    bot,
    route,
    data_dir: Path | None,
) -> tuple[list[int] | None, list[int] | None]:
    """Resolve navigation paths for current->buy and buy->sell.

    Args:
        bot: TradingBot instance
        route: TradeRoute object with buy/sell sectors
        data_dir: Optional TW2002 data directory for twerk pathing

    Returns:
        Tuple of (path_to_buy, path_buy_to_sell) or (None, None) if resolution fails
    """
    path_to_buy: list[int] | None = None
    path_buy_to_sell: list[int] | None = None

    # Prefer twerk data if available.
    if data_dir:
        try:
            graph = await bot.get_sector_map(data_dir)
            if bot.current_sector and route.buy_sector:
                path_to_buy = graph.bfs_path(bot.current_sector, route.buy_sector)
            if route.path and len(route.path) > 1:
                path_buy_to_sell = route.path
            else:
                path_buy_to_sell = graph.bfs_path(route.buy_sector, route.sell_sector)
            return path_to_buy, path_buy_to_sell
        except Exception:
            pass

    # Fall back to in-game knowledge if available.
    if bot.sector_knowledge and bot.current_sector:
        try:
            path_to_buy = bot.sector_knowledge.find_path(bot.current_sector, route.buy_sector)
            path_buy_to_sell = bot.sector_knowledge.find_path(route.buy_sector, route.sell_sector)
        except Exception:
            pass

    return path_to_buy, path_buy_to_sell
