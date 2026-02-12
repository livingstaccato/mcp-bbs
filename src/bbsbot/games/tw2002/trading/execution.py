# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""High-level trading execution and cycle management."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from bbsbot.games.tw2002 import cli_impl
from bbsbot.games.tw2002.io import wait_and_respond
from bbsbot.games.tw2002.parsing import _parse_credits_from_screen, _parse_sector_from_screen
from bbsbot.logging import get_logger

from .navigation import resolve_paths, warp_to_sector
from .operations import dock_and_trade

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


async def execute_route(
    bot,
    route,
    quantity: int | None = None,
    max_retries: int = 2,
    data_dir: Path | None = None,
) -> dict:
    """Execute a twerk-analyzed trade route via terminal.

    This method takes a TradeRoute from twerk analysis and executes it
    through the terminal, navigating to buy sector, buying commodities,
    navigating to sell sector, and selling.

    Args:
        bot: TradingBot instance
        route: TradeRoute object from twerk.analysis containing:
            - buy_sector: Sector ID to buy at
            - sell_sector: Sector ID to sell at
            - commodity: What to trade (fuel_ore, organics, equipment)
            - path: List of sectors from buy to sell
            - max_quantity: Maximum available quantity
        quantity: Units to trade (defaults to route.max_quantity or ship holds)
        max_retries: Maximum retry attempts for recoverable errors
        data_dir: Optional TW2002 data directory for twerk pathing

    Returns:
        Dictionary with trade results:
            - success: bool
            - initial_credits: int
            - final_credits: int
            - profit: int
            - commodity: str
            - quantity_bought: int
            - buy_sector: int
            - sell_sector: int
    """
    print("\n" + "=" * 80)
    print(f"EXECUTING ROUTE: {route.commodity}")
    print(f"  Buy at: {route.buy_sector}")
    print(f"  Sell at: {route.sell_sector}")
    print(f"  Path: {' -> '.join(str(s) for s in route.path)}")
    print("=" * 80)

    # Determine quantity
    trade_quantity = quantity or min(route.max_quantity, 500)  # Default 500 max

    # Track initial state
    initial_credits = bot.current_credits
    result = {
        "success": False,
        "initial_credits": initial_credits,
        "final_credits": initial_credits,
        "profit": 0,
        "commodity": route.commodity,
        "quantity_bought": 0,
        "buy_sector": route.buy_sector,
        "sell_sector": route.sell_sector,
    }

    for attempt in range(max_retries + 1):
        try:
            path_to_buy, path_buy_to_sell = await resolve_paths(bot, route, data_dir)

            # Navigate to buy sector if not already there
            if bot.current_sector != route.buy_sector:
                print(f"\n🚀 NAVIGATE to buy sector {route.buy_sector}")
                if path_to_buy:
                    print(f"  Using path: {' -> '.join(str(s) for s in path_to_buy)}")
                    success = await cli_impl.warp_along_path(bot, path_to_buy)
                    if not success:
                        raise RuntimeError("path_navigation_failed")
                else:
                    await warp_to_sector(bot, route.buy_sector)

            # Update state after navigation
            state = await bot.orient()
            bot.current_sector = state.sector
            if state.credits is not None:
                bot.current_credits = state.credits

            # BUY PHASE
            print(f"\n📍 BUY PHASE (Sector {route.buy_sector})")
            await dock_and_trade(bot, "buy", route.buy_sector, quantity=trade_quantity)
            result["quantity_bought"] = trade_quantity

            # NAVIGATE to sell sector
            if path_buy_to_sell and len(path_buy_to_sell) > 1:
                print("\n🚀 NAVIGATE via route path")
                success = await cli_impl.warp_along_path(bot, path_buy_to_sell)
                if not success:
                    raise RuntimeError("path_navigation_failed")
            else:
                print(f"\n🚀 WARP to {route.sell_sector}")
                await warp_to_sector(bot, route.sell_sector)

            # Update state after navigation
            state = await bot.orient()
            bot.current_sector = state.sector
            if state.credits is not None:
                bot.current_credits = state.credits

            # SELL PHASE
            print(f"\n📍 SELL PHASE (Sector {route.sell_sector})")
            await dock_and_trade(bot, "sell", route.sell_sector)

            # Update state
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
            bot.current_credits = _parse_credits_from_screen(bot, screen)
            bot.current_sector = _parse_sector_from_screen(bot, screen)

            # Calculate profit
            result["final_credits"] = bot.current_credits
            result["profit"] = bot.current_credits - initial_credits
            result["success"] = True

            bot.cycle_count += 1
            print(f"\n✓ Route complete - Profit: {result['profit']:,}")

            return result

        except RuntimeError as e:
            error_msg = str(e)
            print(f"\n⚠️  Route error (attempt {attempt + 1}/{max_retries + 1}): {e}")

            if "insufficient_credits" in error_msg:
                # Reduce quantity and retry
                trade_quantity = max(50, trade_quantity // 2)
                print(f"  → Reducing quantity to {trade_quantity}")
                if attempt < max_retries:
                    continue

            elif "hold_full" in error_msg:
                # Skip to sell phase
                print("  → Hold full, attempting to sell")
                try:
                    await warp_to_sector(bot, route.sell_sector)
                    await dock_and_trade(bot, "sell", route.sell_sector)
                except Exception:
                    pass

            elif "out_of_turns" in error_msg or "ship_destroyed" in error_msg:
                print("  ✗ Fatal error - stopping")
                result["error"] = error_msg
                return result

            if attempt < max_retries:
                wait_time = 2**attempt
                print(f"  → Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                result["error"] = error_msg
                return result

        except TimeoutError as e:
            print(f"\n⚠️  Timeout (attempt {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(1.0)
            else:
                result["error"] = str(e)
                return result

        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            result["error"] = str(e)
            return result

    return result


async def single_trading_cycle(bot, start_sector: int = 499, max_retries: int = 2) -> None:
    """Execute one complete trading cycle (buy→sell) with error recovery.

    Args:
        bot: TradingBot instance
        start_sector: Starting sector (typically 499 or 607)
        max_retries: Maximum retry attempts for recoverable errors

    Raises:
        RuntimeError: On unrecoverable errors
    """
    print("\n" + "=" * 80)
    print(f"TRADING CYCLE: {start_sector} → {607 if start_sector == 499 else 499}")
    print("=" * 80)

    # Determine buying and selling sectors
    buy_sector = start_sector
    sell_sector = 607 if start_sector == 499 else 499

    for attempt in range(max_retries + 1):
        try:
            # Ensure we're at buy sector before trading
            if bot.current_sector is None:
                await bot.orient()
            if bot.current_sector != buy_sector:
                print(f"\n🚀 WARPING to buy sector {buy_sector} (current {bot.current_sector})")
                await warp_to_sector(bot, buy_sector)
                # Verify we arrived at the correct sector
                if bot.current_sector != buy_sector:
                    raise RuntimeError(f"warp_verification_failed:expected_{buy_sector}_got_{bot.current_sector}")

            # BUY PHASE
            print(f"\n📍 BUY PHASE (Sector {buy_sector})")
            try:
                await dock_and_trade(bot, "buy", buy_sector)
            except RuntimeError as e:
                if "insufficient_credits" in str(e):
                    print("  ⚠️  Not enough credits, reducing buy amount")
                    await dock_and_trade(bot, "buy", buy_sector, quantity=100)
                elif "hold_full" in str(e):
                    print("  ⚠️  Hold full, skipping buy phase")
                else:
                    raise

            # WARP PHASE
            print(f"\n🚀 WARPING to {sell_sector}")
            await warp_to_sector(bot, sell_sector)
            # Verify we arrived at the correct sector
            if bot.current_sector != sell_sector:
                raise RuntimeError(f"warp_verification_failed:expected_{sell_sector}_got_{bot.current_sector}")

            # SELL PHASE
            print(f"\n📍 SELL PHASE (Sector {sell_sector})")
            await dock_and_trade(bot, "sell", sell_sector)

            # RETURN WARP
            print(f"\n🚀 WARPING back to {buy_sector}")
            await warp_to_sector(bot, buy_sector)

            bot.cycle_count += 1
            print(f"\n✓ Cycle {bot.cycle_count} complete")
            return  # Success

        except RuntimeError as e:
            error_msg = str(e)
            print(f"\n⚠️  Cycle error (attempt {attempt + 1}/{max_retries + 1}): {e}")

            if "Stuck in loop" in error_msg:
                # Try to escape loop by sending Q or ESC
                print("  → Attempting to escape loop...")
                await bot.session.send("Q")
                await asyncio.sleep(0.5)
                if attempt < max_retries:
                    continue

            elif "out_of_turns" in error_msg:
                print("  ✗ Out of turns - stopping")
                raise

            elif "ship_destroyed" in error_msg:
                print("  ✗ Ship destroyed - stopping")
                raise

            # Other errors - retry if we have attempts left
            if attempt < max_retries:
                wait_time = 2**attempt  # Exponential backoff
                print(f"  → Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                print("  ✗ Max retries reached")
                raise

        except TimeoutError as e:
            print(f"\n⚠️  Timeout (attempt {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries:
                print("  → Retrying...")
                await asyncio.sleep(1.0)
            else:
                raise

        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            raise
