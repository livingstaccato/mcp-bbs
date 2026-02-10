#!/usr/bin/env python3
"""Trace raw session behavior after game selection."""

import asyncio

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import send_input


async def debug_raw_session():
    """Trace what's actually happening in the session."""
    print("\n" + "=" * 80)
    print("DEBUG: Raw Session Behavior After Game Selection")
    print("=" * 80)

    bot = TradingBot()

    try:
        # Connect
        await connect(bot)
        print("✓ Connected\n")

        # Navigate to game selection
        print("Getting to menu_selection prompt...")
        for _step in range(5):
            snapshot = await bot.session.read(timeout_ms=500, max_bytes=8192)
            detected = snapshot.get("prompt_detected")

            if detected and "menu_selection" in detected.get("prompt_id", ""):
                print("✓ Found menu_selection\n")
                detected.get("prompt_id")
                detected.get("input_type")
                break

            # Try to handle login
            if detected and "login_name" in detected.get("prompt_id", ""):
                await send_input(bot, "testbot", detected.get("input_type"))

        # Now send "B"
        print("Sending 'B' to select game...")
        await bot.session.send("B")
        print("✓ Sent 'B'\n")

        # Now let's check session health
        print("Checking session health after sending 'B'...")
        print("-" * 80)

        for i in range(5):
            try:
                print(f"\nRead attempt #{i + 1}:")
                snapshot = await bot.session.read(timeout_ms=1000, max_bytes=8192)

                # Check for errors
                screen = snapshot.get("screen", "")
                detected = snapshot.get("prompt_detected")
                error = snapshot.get("error")

                print(f"  Screen length: {len(screen)}")
                print(f"  Prompt detected: {detected is not None}")
                print(f"  Error in snapshot: {error is not None}")

                if error:
                    print(f"  ERROR DETAIL: {error}")

                if detected:
                    print(f"  Prompt ID: {detected.get('prompt_id')}")
                    print(f"  Is idle: {detected.get('is_idle')}")
                    print(f"  Input type: {detected.get('input_type')}")

                    # Show screen preview
                    preview = screen[:200] if screen else "(empty)"
                    print(f"  Screen preview: {preview}")

                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"  Exception during read: {e}")
                import traceback

                traceback.print_exc()

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)


if __name__ == "__main__":
    try:
        asyncio.run(debug_raw_session())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
