# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Trading module - modular trading operations for TW2002."""

from __future__ import annotations

from bbsbot.games.tw2002.io import wait_and_respond
from bbsbot.games.tw2002.logging_utils import _print_session_summary, _save_trade_history, logger
from bbsbot.games.tw2002.parsing import _parse_credits_from_screen, _parse_sector_from_screen

# Re-export public APIs for backward compatibility
from .execution import execute_route, single_trading_cycle
from .navigation import navigate_path, resolve_paths, warp_to_sector
from .operations import dock_and_trade
from .parsers import extract_sector_from_screen
from .validation import extract_port_info, guard_trade_port, is_trade_port_class, validate_kv_data

__all__ = [
    # Main loop
    "run_trading_loop",
    # Execution
    "execute_route",
    "single_trading_cycle",
    # Navigation
    "warp_to_sector",
    "navigate_path",
    "resolve_paths",
    # Operations
    "dock_and_trade",
    # Parsing
    "extract_sector_from_screen",
    # Validation
    "validate_kv_data",
    "is_trade_port_class",
    "extract_port_info",
    "guard_trade_port",
]


async def run_trading_loop(bot, target_credits: int = 5_000_000, max_cycles: int = 20) -> None:
    """Run trading loop until target credits or max cycles.

    Args:
        bot: TradingBot instance
        target_credits: Target credit amount
        max_cycles: Maximum cycles to run

    Raises:
        Exception: On fatal trading errors
    """
    from bbsbot.games.tw2002.connection import connect
    from bbsbot.games.tw2002.login import login_sequence

    print("\n" + "=" * 80)
    print(f"TRADING LOOP: Target {target_credits:,} credits")
    print("=" * 80)

    try:
        await connect(bot)
        await login_sequence(bot)

        # Save initial credits
        bot.initial_credits = bot.current_credits
        logger.info(
            "trading_loop_start",
            target_credits=target_credits,
            initial_credits=bot.initial_credits,
            max_cycles=max_cycles,
        )

        for cycle in range(max_cycles):
            if bot.current_credits >= target_credits:
                print(f"\n✓ Target reached: {bot.current_credits:,} / {target_credits:,}")
                logger.info("target_reached", credits=bot.current_credits)
                break

            print(f"\nCycle {cycle + 1}/{max_cycles} - Credits: {bot.current_credits:,}")
            logger.info(
                "cycle_start",
                cycle=cycle + 1,
                credits=bot.current_credits,
                sector=bot.current_sector,
            )

            await single_trading_cycle(bot, start_sector=499)

            # Update credits from screen
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
            bot.current_credits = _parse_credits_from_screen(bot, screen)
            bot.current_sector = _parse_sector_from_screen(bot, screen)

            logger.info(
                "cycle_complete",
                cycle=cycle + 1,
                credits=bot.current_credits,
                profit=bot.current_credits - bot.initial_credits,
            )

    except Exception as e:
        print(f"\n✗ Trading loop failed: {e}")
        logger.error("trading_loop_failed", error=str(e), error_type=type(e).__name__)
        raise
    finally:
        # Print summary and save logs
        _print_session_summary(bot)
        _save_trade_history(bot)

        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)
