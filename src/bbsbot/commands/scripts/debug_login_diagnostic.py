#!/usr/bin/env python3
"""Interactive login diagnostic tool.

Walks through login step-by-step, showing:
- Actual screen content
- Detected prompt
- What to watch for
"""

import asyncio

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import wait_and_respond


async def analyze_screen(bot, step_num: int, screen: str, prompt_id: str, input_type: str):
    """Analyze a screen and report findings."""

    print(f"\n{'=' * 80}")
    print(f"STEP {step_num}: {prompt_id}")
    print(f"{'=' * 80}")

    # Show screen excerpt
    print("\n📺 SCREEN CONTENT (showing content):")
    print("-" * 80)
    lines = screen.split("\n")

    # Show last 30 lines (end of screen is usually where prompt is)
    start_idx = max(0, len(lines) - 30)
    for i, line in enumerate(lines[start_idx:], start=start_idx):
        # Truncate long lines
        if len(line) > 78:
            print(f"{i:2}: {line[:75]}...")
        else:
            print(f"{i:2}: {line}")
    print("-" * 80)

    # Show detected prompt info
    print(f"\n🎯 DETECTED PROMPT: {prompt_id}")
    print(f"   Input type: {input_type}")

    # Analysis
    print("\n🔍 ANALYSIS:")
    screen_lower = screen.lower()

    # Check basic expectations
    if prompt_id == "NONE" or prompt_id is None or prompt_id == "":
        print("   ❌ NO PROMPT DETECTED")
        print("      This screen didn't match any pattern")
        print("      → Look at screen content above")
        print("      → What text appears at the prompt line?")
    else:
        print(f"   ✓ Detected: {prompt_id}")

    # Check for mismatches
    if "login" in screen_lower and "name" in screen_lower and "login_name" not in prompt_id:
        print("   ⚠️  MISMATCH: Screen shows login name prompt")
        print(f"      but detected: {prompt_id}")

    if "password" in screen_lower and "password" not in prompt_id.lower():
        print("   ⚠️  MISMATCH: Screen shows password prompt")
        print(f"      but detected: {prompt_id}")

    if "[pause]" in screen_lower and "pause" not in prompt_id:
        print("   ⚠️  MISMATCH: Screen shows [pause]")
        print(f"      but detected: {prompt_id}")

    # Check for errors
    if any(x in screen_lower for x in ["invalid", "error", "not found", "failed"]):
        print("   ⚠️  ERROR DETECTED on screen:")
        for i, line in enumerate(lines):
            if any(x in line.lower() for x in ["invalid", "error", "not found", "failed"]):
                print(f"      Line {i}: {line}")

    print(f"\n{'=' * 80}")


async def main():
    print(f"\n{'=' * 80}")
    print("LOGIN DIAGNOSTIC TOOL")
    print("=" * 80)
    print("""
This tool shows you exactly what the bot sees at each login step.

WHAT TO LOOK FOR:
1. Do prompts match what you see on screen?
2. Are error messages appearing?
3. Is the bot stuck in a loop?
4. What happens at each pause screen?

CONTROLS:
- ENTER = continue (bot handles next step)
- 'S' + input = send custom input
- 'Q' = quit diagnostic
    """)

    username = input("\nUsername (default: testbot): ").strip() or "testbot"
    password = input("Character password (default: test): ").strip() or "test"
    game_password = input("Game password (default: game): ").strip() or "game"

    print("\nConnecting with:")
    print(f"  Username: {username}")
    print(f"  Password: {password}")
    print(f"  Game password: {game_password}\n")

    bot = TradingBot()

    try:
        print("🔗 Connecting to BBS...")
        await connect(bot)
        print("✓ Connected\n")

        step = 0
        login_name_sent = False
        menu_selection_found = False

        # PHASE 1: Navigate to game selection
        print("=" * 80)
        print("PHASE 1: Navigate to game selection")
        print("=" * 80)

        for attempt in range(20):
            step += 1
            try:
                input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=8000)
            except TimeoutError:
                print(f"\n❌ TIMEOUT at step {step}")
                print("   No prompt received for 8 seconds")
                print("\n   This could mean:")
                print("   - Connection dropped")
                print("   - Bot waiting for something it doesn't recognize")
                print("   - Network issue")
                return

            await analyze_screen(bot, step, screen, prompt_id, input_type)

            response = input("\n➜ Action (ENTER=continue, S=send, Q=quit): ").strip().upper()

            if response == "Q":
                return
            elif response == "S":
                what_to_send = input("   Send what? ").strip()
                await bot.session.send(what_to_send)
                await asyncio.sleep(0.3)
                continue

            # Auto-handle prompts
            if "login_name" in prompt_id and not login_name_sent:
                print(f"\n→ Auto-sending username: {username}")
                await bot.session.send(username)
                await asyncio.sleep(0.3)
                login_name_sent = True

            elif "menu_selection" in prompt_id:
                print("\n✓ Reached menu selection!")
                menu_selection_found = True
                break

            elif input_type == "any_key":
                print("\n→ Auto-sending space (any_key)")
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

            else:
                print("\n→ Auto-sending space")
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

        if not menu_selection_found:
            print("\n⚠️  Did not reach menu_selection")
            return

        # PHASE 2: Send game selection
        print("\n" + "=" * 80)
        print("PHASE 2: Send game selection")
        print("=" * 80)
        print("→ Sending 'B' to select game")
        await bot.session.send("B")
        await asyncio.sleep(0.5)

        # PHASE 3: Wait for game load
        print("\n" + "=" * 80)
        print("PHASE 3: Game loading (watch for patterns)")
        print("=" * 80)

        pause_count = 0
        for phase3_step in range(65):
            step += 1
            try:
                input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=20000)
            except TimeoutError:
                print(f"\n❌ TIMEOUT at step {step}")
                print("   Game load exceeded 20 seconds")
                return

            # Track pause prompts
            if "pause" in prompt_id:
                pause_count += 1

            # Only show every 5th step during loading to reduce spam
            if pause_count % 5 == 1 or "pause" not in prompt_id:
                await analyze_screen(bot, step, screen, prompt_id, input_type)
                response = input("\n➜ Action (ENTER=continue, S=send, Q=quit): ").strip().upper()

                if response == "Q":
                    return
                elif response == "S":
                    what_to_send = input("   Send what? ").strip()
                    await bot.session.send(what_to_send)
                    await asyncio.sleep(0.3)
                    continue

            # Auto-handle game load phase
            if "password" in prompt_id:
                print("  → Sending game password")
                await bot.session.send(game_password)
                await asyncio.sleep(0.3)

            elif "command" in prompt_id or "sector" in prompt_id:
                print("\n✅ LOGIN COMPLETE!")
                print(f"   Final prompt: {prompt_id}")
                return

            elif input_type == "any_key":
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

            else:
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

        print(f"\n⚠️  Did not reach command prompt after {step} steps")

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
        print("\n\nInterrupted by user")
