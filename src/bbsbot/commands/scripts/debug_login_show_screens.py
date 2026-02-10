#!/usr/bin/env python3
"""Auto-running login diagnostic - shows each screen and analysis."""

import asyncio

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import wait_and_respond


async def show_step(step_num, screen, prompt_id, input_type):
    """Display one login step with analysis."""

    print(f"\n{'▼' * 80}")
    print(f"STEP {step_num}: {prompt_id} ({input_type})")
    print(f"{'▼' * 80}")

    # Show last 25 lines of screen
    lines = screen.split("\n")
    start = max(0, len(lines) - 25)

    for i, line in enumerate(lines[start:], start=start):
        if len(line) > 78:
            print(f"{i:2d}: {line[:75]}...")
        else:
            print(f"{i:2d}: {line}")

    # Analysis
    print(f"\n{'─' * 80}")
    print(f"DETECTED: {prompt_id}")
    print(f"INPUT TYPE: {input_type}")

    screen_lower = screen.lower()

    # Check for issues
    issues = []
    if len(screen.strip()) < 50:
        issues.append("Screen very short")
    if "invalid" in screen_lower:
        issues.append("Contains 'invalid'")
    if "error" in screen_lower:
        issues.append("Contains 'error'")
    if "not found" in screen_lower:
        issues.append("Contains 'not found'")

    if issues:
        print(f"⚠️  POTENTIAL ISSUES: {', '.join(issues)}")
    else:
        print("✓ Screen looks normal")

    return prompt_id, input_type


async def main():
    print(f"\n{'═' * 80}")
    print("  AUTOMATED LOGIN DIAGNOSTIC")
    print(f"{'═' * 80}")
    print("\nThis will walk through login showing each screen.\n")

    bot = TradingBot()

    try:
        print("Connecting...")
        await connect(bot)
        print("✓ Connected\n")

        step = 0

        # PHASE 1: To menu selection
        print(f"\n{'═' * 80}")
        print("PHASE 1: Login → Menu Selection")
        print(f"{'═' * 80}")

        for attempt in range(15):
            step += 1
            try:
                input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=8000)
            except TimeoutError:
                print(f"\n❌ TIMEOUT at step {step} - no prompt for 8 seconds")
                return

            await show_step(step, screen, prompt_id, input_type)

            # Handle prompts
            if "login_name" in prompt_id:
                print("\n→ Sending username 'testbot'")
                await bot.session.send("testbot")
                await asyncio.sleep(0.3)

            elif "menu_selection" in prompt_id:
                print("\n✓ REACHED MENU SELECTION")
                break

            elif input_type == "any_key":
                print("\n→ Sending space")
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

            else:
                print("\n→ Sending space")
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

        # PHASE 2: Game selection
        print(f"\n{'═' * 80}")
        print("PHASE 2: Send Game Selection")
        print(f"{'═' * 80}")
        print("→ Sending 'B' to select game")
        await bot.session.send("B")
        await asyncio.sleep(0.5)

        # PHASE 3: Game load
        print(f"\n{'═' * 80}")
        print("PHASE 3: Game Loading")
        print(f"{'═' * 80}")
        print("(Showing screens, will skip repetitive pause prompts)")

        pause_count = 0
        last_prompt_id = None

        for attempt in range(70):
            step += 1
            try:
                input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=20000)
            except TimeoutError:
                print("\n❌ TIMEOUT - game load exceeded 20 seconds")
                return

            # Track pauses, show every 10th or if different
            if "pause" in prompt_id:
                pause_count += 1
                if pause_count % 10 != 1 and prompt_id == last_prompt_id:
                    # Skip repetitive pauses
                    print(f"  Step {step}: {prompt_id} (#{pause_count}, skipping display)")
                    await bot.session.send(" ")
                    await asyncio.sleep(0.2)
                    continue

            await show_step(step, screen, prompt_id, input_type)
            last_prompt_id = prompt_id

            # Handle
            if "password" in prompt_id:
                print("\n→ Sending game password")
                await bot.session.send("game")
                await asyncio.sleep(0.3)

            elif "command" in prompt_id or "sector" in prompt_id:
                print(f"\n{'✓' * 40}")
                print("✓ LOGIN COMPLETE - Reached command prompt!")
                print(f"{'✓' * 40}")
                return

            elif input_type == "any_key":
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

            else:
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

        print("\n❌ Did not reach command prompt")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted")
