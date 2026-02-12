#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Test bot with brand new character."""

import asyncio
import sys
import time

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.login import login_sequence
from bbsbot.games.tw2002.trading import single_trading_cycle


async def main():
    # Use timestamp for unique character
    timestamp = str(int(time.time()))[-6:]  # Last 6 digits
    char_name = f"bot{timestamp}"
    char_pass = char_name
    game_pass = "game"

    print(f"\n{'═' * 80}")
    print("🚀 CREATING NEW CHARACTER")
    print(f"{'═' * 80}")
    print(f"Character: {char_name}")
    print(f"Password: {char_pass}")
    print("Server: localhost:2002")
    print(f"{'═' * 80}\n")

    bot = TradingBot()

    try:
        print("📡 Connecting to BBS...")
        await connect(bot)
        print("✓ Connected\n")

        print("🔐 Running login sequence...")
        await login_sequence(bot, game_password=game_pass, character_password=char_pass, username=char_name)
        print(f"\n✓ Login complete for character: {char_name}\n")

        print("🎮 Running trading cycle...")
        await single_trading_cycle(bot, start_sector=499)

        print(f"\n{'═' * 80}")
        print(f"✅ SUCCESS: Bot created character '{char_name}' and traded successfully!")
        print(f"{'═' * 80}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

    return True


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
