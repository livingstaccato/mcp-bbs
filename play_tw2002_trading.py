#!/usr/bin/env python3
"""TW2002 Trading Bot - CLI Entry Point

Automated credit accumulation via 499↔607 trading loop.
"""

import asyncio
import sys
from argparse import ArgumentParser

from twbot import TradingBot


async def main():
    parser = ArgumentParser(description="TW2002 Trading Bot")
    parser.add_argument(
        "--test-login",
        action="store_true",
        help="Test login sequence only",
    )
    parser.add_argument(
        "--single-cycle",
        action="store_true",
        help="Run single trading cycle",
    )
    parser.add_argument(
        "--start-sector",
        type=int,
        default=499,
        help="Starting sector for trading (default: 499)",
    )
    parser.add_argument(
        "--target-credits",
        type=int,
        default=5_000_000,
        help="Target credit amount (default: 5,000,000)",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=20,
        help="Maximum trading cycles (default: 20)",
    )

    args = parser.parse_args()
    bot = TradingBot()

    try:
        if args.test_login:
            success = await bot.test_login()
            sys.exit(0 if success else 1)

        elif args.single_cycle:
            await bot.connect()
            await bot.login_sequence()
            await bot.single_trading_cycle(start_sector=args.start_sector)
            print("\n✓ Single cycle test passed")

        else:
            # Full trading loop
            await bot.run_trading_loop(
                target_credits=args.target_credits, max_cycles=args.max_cycles
            )

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        if bot.session_id:
            try:
                await bot.session_manager.close_session(bot.session_id)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
