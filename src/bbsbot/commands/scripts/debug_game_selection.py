#!/usr/bin/env python3
"""Debug what happens after game selection."""

import asyncio
import sys
import time
from pathlib import Path


from bbsbot.tw2002 import TradingBot
from bbsbot.tw2002.connection import connect
from bbsbot.tw2002.io import wait_and_respond, send_input


async def debug_game_selection():
    """Debug the game selection sequence."""
    print("\n" + "=" * 80)
    print("DEBUG: Game Selection Sequence")
    print("=" * 80)

    bot = TradingBot()

    try:
        # Connect
        await connect(bot)
        print("✓ Connected")

        # Navigate to game selection menu
        print("\nPhase 1: Navigate to menu_selection prompt...")
        for step in range(5):
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=5000
            )
            print(f"  Step {step}: {prompt_id}")

            if "menu_selection" in prompt_id:
                print(f"✓ Found menu_selection prompt")
                print(f"  Input type: {input_type}")
                print(f"  Screen preview: {screen[:200]}")
                break

            # Handle login prompts
            if "login_name" in prompt_id:
                await send_input(bot, "testbot", input_type)
            elif "login_password" in prompt_id:
                await send_input(bot, "test", input_type)
            elif input_type == "any_key":
                await send_input(bot, "", input_type)

        # Now send game selection and monitor what happens
        print("\n" + "-" * 80)
        print("Phase 2: Send game selection 'B'...")
        print("-" * 80)

        await bot.session.send("B")
        print("✓ Sent 'B' to select game")

        # Now let's see what happens - trace at a lower level
        print("\nPhase 3: Monitor session.read() directly after sending 'B'...")
        print("(This bypasses wait_and_respond to see raw behavior)")
        print()

        start_time = time.time()
        read_count = 0
        last_screen = ""
        last_prompt_id = None
        last_is_idle = False

        while time.time() - start_time < 15:  # 15 seconds
            read_count += 1
            try:
                snapshot = await bot.session.read(timeout_ms=250, max_bytes=8192)

                screen = snapshot.get("screen", "")
                detected = snapshot.get("prompt_detected")

                elapsed = time.time() - start_time
                screen_changed = screen != last_screen
                screen_len = len(screen)

                print(f"[{elapsed:6.2f}s] Read #{read_count:2d}: ", end="")

                if detected:
                    prompt_id = detected.get("prompt_id")
                    is_idle = detected.get("is_idle", False)
                    input_type = detected.get("input_type")

                    status = "✓ IDLE" if is_idle else "⏳ BUSY"
                    print(
                        f"{status} | prompt={prompt_id:25s} | input={input_type:10s} | len={screen_len}"
                    )

                    if prompt_id != last_prompt_id:
                        print(f"             Screen first 150 chars: {screen[:150]}")

                    last_prompt_id = prompt_id
                    last_is_idle = is_idle

                    if is_idle:
                        print(f"\n✓ REACHED IDLE STATE AT {elapsed:.2f}s")
                        print(f"  Prompt: {prompt_id}")
                        print(f"  Input type: {input_type}")
                        break

                else:
                    print(
                        f"⚠️  NO PROMPT | screen_len={screen_len} | changed={screen_changed}"
                    )

                last_screen = screen

            except Exception as e:
                print(f"✗ Error during read: {e}")
                break

            await asyncio.sleep(0.05)  # Small delay between reads

        if not last_is_idle:
            print(f"\n✗ TIMEOUT: Never reached idle state in 15 seconds")
            print(f"  Last prompt detected: {last_prompt_id}")
            print(f"  Last screen (first 500 chars):")
            print(f"  {last_screen[:500]}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)


if __name__ == "__main__":
    try:
        asyncio.run(debug_game_selection())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
