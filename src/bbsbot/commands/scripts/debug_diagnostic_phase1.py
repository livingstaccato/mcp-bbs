#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Use diagnostic's Phase 1 logic exactly."""

import asyncio

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import send_input, wait_and_respond


async def test():
    """Use diagnostic's exact Phase 1 + game selection + Phase 3."""
    print("\n" + "=" * 80)
    print("DIAGNOSTIC PHASE 1 LOGIC")
    print("=" * 80)

    bot = TradingBot()

    try:
        await connect(bot)
        print("✓ Connected\n")

        # PHASE 1: Copy diagnostic's exact loop
        print("Phase 1: Navigate to menu_selection (diagnostic loop)...")
        for step in range(5):
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)
            print(f"  Step {step}: {prompt_id}")

            if "menu_selection" in prompt_id:
                print("✓ Found menu_selection prompt\n")
                break

            # Handle login prompts like diagnostic
            if "login_name" in prompt_id:
                print("  Handling login_name")
                await send_input(bot, "testbot", input_type)
            elif "login_password" in prompt_id:
                await send_input(bot, "test", input_type)
            elif input_type == "any_key":
                await send_input(bot, "", input_type)

        # PHASE 2: Send B
        print("Phase 2: Sending 'B'...")
        await bot.session.send("B")
        print("✓ Sent 'B'\n")

        # PHASE 3: This is where bot fails
        print("Phase 3: Wait for next prompt...")
        try:
            input_type3, prompt_id3, screen3, kv_data3 = await wait_and_respond(
                bot,
                timeout_ms=15000,  # Use same 15s as diagnostic
            )
            print(f"✓ SUCCESS: Got {prompt_id3} ({input_type3})")
            return True
        except TimeoutError as e:
            print(f"✗ TIMEOUT: {e}")
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
        result = asyncio.run(test())
        if result:
            print("\n✅ PASSED")
        else:
            print("\n❌ FAILED")
    except KeyboardInterrupt:
        print("\n\nInterrupted")
