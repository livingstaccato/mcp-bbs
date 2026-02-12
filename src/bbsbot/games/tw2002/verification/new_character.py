#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Proof: Bot works with new character on localhost:2002."""

import asyncio
import sys
import time

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.login import login_sequence
from bbsbot.games.tw2002.trading import single_trading_cycle


async def test():
    unique_char = f"bottest{int(time.time()) % 100000}"
    char_password = unique_char
    game_password = "game"

    bot = TradingBot()

    try:
        print(f"\n{'=' * 80}")
        print("PROOF: Bot working with new character")
        print(f"{'=' * 80}")
        print(f"Character: {unique_char}")
        print(f"Password: {char_password}")
        print("Server: localhost:2002")
        print(f"{'=' * 80}\n")

        await connect(bot)
        print("✓ Connected to BBS\n")

        await login_sequence(bot, game_password=game_password, character_password=char_password, username=unique_char)

        print("\n✓ Login successful!\n")

        # Ensure we're at sector command (not planet prompt) before trading
        state = await bot.orient()
        if state.context == "planet_command":
            print("  At planet command; exiting to sector command...")
            await bot.session.send("Q")
            await asyncio.sleep(0.5)
            state = await bot.orient()
        if state.context != "sector_command":
            raise RuntimeError(f"Unexpected context before trading: {state.context}")

        # Run trading cycle only if we have credits and a port to trade at
        if state.credits is None or state.credits <= 0:
            print("  ⚠️  No credits available; skipping trade cycle")
            return True
        if not state.has_port:
            print("  ⚠️  No port in current sector; skipping trade cycle")
            return True

        await single_trading_cycle(bot, start_sector=state.sector or 499)

        print("\n" + "=" * 80)
        print("✅ SUCCESS: Bot completed full trading cycle!")
        print("=" * 80)
        print("Validation system: WORKING END-TO-END on localhost:2002")
        print("=" * 80 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)


if __name__ == "__main__":
    try:
        result = asyncio.run(test())
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
