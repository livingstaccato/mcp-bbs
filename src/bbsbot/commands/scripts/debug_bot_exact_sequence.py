#!/usr/bin/env python3
"""Replicate the exact bot login sequence to debug where it fails."""

import asyncio
import sys
from pathlib import Path


from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import wait_and_respond, send_input


async def test_exact_sequence():
    """Replicate bot's exact sequence."""
    print("\n" + "=" * 80)
    print("EXACT BOT SEQUENCE DEBUG")
    print("=" * 80)

    bot = TradingBot()

    try:
        # Step 0: Connect (just like bot)
        await connect(bot)
        print("✓ Connected\n")

        # Step 1: Get login_name prompt (like bot loop iteration 1)
        print("Step 1: Call wait_and_respond() for login_name...")
        input_type1, prompt_id1, screen1, kv_data1 = await wait_and_respond(
            bot, timeout_ms=20000
        )
        print(f"  Got: {prompt_id1} ({input_type1})")

        # Handle it like bot does (skip telnet login)
        if "login_name" in prompt_id1 and "telnet" in screen1.lower():
            print("  → Skipping telnet login")
            await bot.session.send("\r")
            await asyncio.sleep(0.3)
        elif "login_name" in prompt_id1:
            print("  → Sending username")
            await send_input(bot, "testbot", input_type1)

        # Step 2: Get menu_selection prompt (like bot loop iteration 2)
        print("\nStep 2: Call wait_and_respond() for menu_selection...")
        input_type2, prompt_id2, screen2, kv_data2 = await wait_and_respond(
            bot, timeout_ms=20000
        )
        print(f"  Got: {prompt_id2} ({input_type2})")

        # Handle it like bot does (send game selection)
        if "menu_selection" in prompt_id2:
            print("  → Sending B to select game (single key, no return)")
            await bot.session.send("B")  # NO sleep after, matching new version
            # await asyncio.sleep(0.5)  # REMOVED

        # Step 3: This is where bot times out
        print("\nStep 3: Call wait_and_respond() for next prompt...")
        print("  (This is where the bot times out)")
        try:
            input_type3, prompt_id3, screen3, kv_data3 = await wait_and_respond(
                bot, timeout_ms=20000
            )
            print(f"  ✓ SUCCESS: Got {prompt_id3} ({input_type3})")
        except TimeoutError as e:
            print(f"  ✗ TIMEOUT: {e}")
            print(f"\n  Bot state at failure:")
            print(f"    step_count: {bot.step_count}")
            print(f"    last_prompt_id: {bot.last_prompt_id}")
            print(f"    loop_detection: {bot.loop_detection}")
            raise

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(test_exact_sequence())
        if result:
            print("\n✅ Exact sequence test PASSED")
        else:
            print("\n❌ Exact sequence test FAILED")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
