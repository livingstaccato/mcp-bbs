#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Test: Skip first 2 waits, go directly to game selection (like diagnostic does)."""

import asyncio

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import wait_and_respond


async def test_skip_first_two():
    """Skip first two waits, go directly to menu selection and send B."""
    print("\n" + "=" * 80)
    print("SKIP FIRST TWO - DIRECT TO GAME SELECTION")
    print("=" * 80)

    bot = TradingBot()

    try:
        # Step 0: Connect
        await connect(bot)
        print("✓ Connected\n")

        # SKIP Step 1 and 2, go directly to menu_selection
        # Get menu_selection prompt WITHOUT doing prior waits
        print("Getting menu_selection prompt (skipping login_name)...")
        input_type2, prompt_id2, screen2, kv_data2 = await wait_and_respond(bot, timeout_ms=20000)
        print(f"  Got: {prompt_id2} ({input_type2})")

        # Try to find and skip past login_name if we got it
        if "login_name" in prompt_id2:
            print("  Got login_name instead, handling it...")
            await bot.session.send("\r")
            await asyncio.sleep(0.3)
            # Try again for menu_selection
            input_type2, prompt_id2, screen2, kv_data2 = await wait_and_respond(bot, timeout_ms=20000)
            print(f"  Now got: {prompt_id2} ({input_type2})")

        if "menu_selection" not in prompt_id2:
            print(f"ERROR: Expected menu_selection, got {prompt_id2}")
            return False

        # Send B
        print("  → Sending B")
        await bot.session.send("B")

        # Now the key test: can we get the next prompt?
        print("\nWaiting for next prompt after sending B...")
        try:
            input_type3, prompt_id3, screen3, kv_data3 = await wait_and_respond(bot, timeout_ms=20000)
            print(f"  ✓ SUCCESS: Got {prompt_id3} ({input_type3})")
            return True
        except TimeoutError as e:
            print(f"  ✗ TIMEOUT: {e}")
            return False

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)


if __name__ == "__main__":
    try:
        result = asyncio.run(test_skip_first_two())
        if result:
            print("\n✅ Skip-first-two test PASSED")
        else:
            print("\n❌ Skip-first-two test FAILED")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
