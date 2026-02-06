#!/usr/bin/env python3
"""Detailed debug of what happens during and after game selection."""

import asyncio
import sys
import time
from pathlib import Path


from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import wait_and_respond, send_input


async def debug_with_instrumentation():
    """Debug with instrumentation to see exactly what's happening."""
    print("\n" + "=" * 80)
    print("DEBUG: Game Selection with Wait Detection")
    print("=" * 80)

    bot = TradingBot()

    try:
        # Connect
        await connect(bot)
        print("✓ Connected\n")

        # Navigate to game selection menu
        print("Step 1: Get to menu_selection prompt...")
        for step in range(5):
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=5000
            )

            if "menu_selection" in prompt_id:
                print(f"✓ Found menu_selection prompt\n")
                break

            # Handle login prompts
            if "login_name" in prompt_id:
                await send_input(bot, "testbot", input_type)
            elif "login_password" in prompt_id:
                await send_input(bot, "test", input_type)
            elif input_type == "any_key":
                await send_input(bot, "", input_type)

        # Now send game selection
        print("Step 2: Sending 'B' to select game...")
        await bot.session.send("B")
        print("✓ Sent 'B'\n")

        # Now use wait_and_respond with instrumentation
        print(
            "Step 3: Using wait_and_respond() to get next prompt (this is what fails)...\n"
        )
        print("Monitoring internally...")

        start = time.time()
        try:
            # This is the call that times out
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=15000
            )
            elapsed = time.time() - start
            print(f"\n✓ Got prompt after {elapsed:.2f}s")
            print(f"  Prompt: {prompt_id}")
            print(f"  Input type: {input_type}")

        except TimeoutError as e:
            elapsed = time.time() - start
            print(f"\n✗ Timeout after {elapsed:.2f}s: {e}")
            print(f"\nLast detected prompts:")
            for p in bot.detected_prompts[-5:]:
                print(
                    f"  Step {p['step']}: {p['prompt_id']} ({p.get('input_type', 'unknown')})"
                )
            print(f"\nLoop detection state: {bot.loop_detection}")
            print(f"Last prompt: {bot.last_prompt_id}")

        except RuntimeError as e:
            elapsed = time.time() - start
            print(f"\n✗ RuntimeError after {elapsed:.2f}s: {e}")
            print(f"\nLast detected prompts:")
            for p in bot.detected_prompts[-5:]:
                print(
                    f"  Step {p['step']}: {p['prompt_id']} ({p.get('input_type', 'unknown')})"
                )
            print(f"\nLoop detection state: {bot.loop_detection}")
            print(f"Last prompt: {bot.last_prompt_id}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)


if __name__ == "__main__":
    try:
        asyncio.run(debug_with_instrumentation())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
