#!/usr/bin/env python3
"""TW2002 Trading Bot - CLI Entry Point

Automated credit accumulation via 499↔607 trading loop.
"""

import asyncio
import sys
from argparse import ArgumentParser

from bbsbot.tw2002 import TradingBot


async def main():
    parser = ArgumentParser(description="TW2002 Trading Bot")
    parser.add_argument(
        "--test-login",
        action="store_true",
        help="Test login sequence only",
    )
    parser.add_argument(
        "--orient",
        action="store_true",
        help="Test login and orientation (determine where we are)",
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
    parser.add_argument(
        "--username",
        type=str,
        default="claude",
        help="Character name (default: claude)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="BBS host (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2002,
        help="BBS port (default: 2002)",
    )

    args = parser.parse_args()
    bot = TradingBot(character_name=args.username)

    try:
        if args.test_login:
            success = await bot.test_login()
            sys.exit(0 if success else 1)

        elif args.orient:
            # Test login + orientation
            await bot.connect(host=args.host, port=args.port)
            await bot.login_sequence(username=args.username)

            # Initialize knowledge and orient
            bot.init_knowledge(host=args.host, port=args.port)
            state = await bot.orient()

            print("\n" + "=" * 60)
            print("ORIENTATION COMPLETE")
            print("=" * 60)
            print(f"  Context:    {state.context}")
            print(f"  Sector:     {state.sector}")
            print(f"  Credits:    {state.credits:,}" if state.credits else "  Credits:    Unknown")
            print(f"  Turns:      {state.turns_left}" if state.turns_left else "  Turns:      Unknown")
            print(f"  Fighters:   {state.fighters}" if state.fighters else "  Fighters:   Unknown")
            print(f"  Shields:    {state.shields}" if state.shields else "  Shields:    Unknown")
            print(f"  Ship:       {state.ship_type}" if state.ship_type else "  Ship:       Unknown")
            print(f"  Warps:      {state.warps}")
            print(f"  Port:       {state.port_class}" if state.has_port else "  Port:       None")
            print(f"  Planet:     {', '.join(state.planet_names)}" if state.has_planet else "  Planet:     None")
            print(f"  Known sectors: {bot.sector_knowledge.known_sector_count()}")
            print("=" * 60)

        elif args.single_cycle:
            await bot.connect(host=args.host, port=args.port)
            await bot.login_sequence(username=args.username)

            # Orient first to know where we are
            bot.init_knowledge(host=args.host, port=args.port)
            state = await bot.orient()
            print(f"\n[Oriented] {state.summary()}")

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
