#!/usr/bin/env python3
"""Login diagnostic - CORRECT VERSION using send_input()."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from twbot import TradingBot
from twbot.connection import connect
from twbot.io import wait_and_respond, send_input

async def show_step(step_num, screen, prompt_id, input_type):
    """Display one login step with analysis."""
    
    print(f"\n{'▼' * 80}")
    print(f"STEP {step_num}: {prompt_id} ({input_type})")
    print(f"{'▼' * 80}")
    
    # Show last 20 lines of screen
    lines = screen.split('\n')
    start = max(0, len(lines) - 20)
    
    for i, line in enumerate(lines[start:], start=start):
        if len(line) > 78:
            print(f"{i:2d}: {line[:75]}...")
        else:
            print(f"{i:2d}: {line}")
    
    # Analysis
    print(f"\n{'─' * 80}")
    print(f"✓ DETECTED: {prompt_id} ({input_type})")
    
    screen_lower = screen.lower()
    
    # Check for issues
    issues = []
    if "invalid" in screen_lower:
        issues.append("Contains 'invalid'")
    if "error" in screen_lower:
        issues.append("Contains 'error'")
    if "incorrect" in screen_lower:
        issues.append("Contains 'incorrect'")
    
    if issues:
        print(f"⚠️  ISSUES: {', '.join(issues)}")

async def main():
    print(f"\n{'═' * 80}")
    print(f"  LOGIN DIAGNOSTIC (CORRECTED)")
    print(f"{'═' * 80}")
    print(f"\nThis shows correct use of send_input() with \\r newlines.\n")
    
    bot = TradingBot()
    
    try:
        print("Connecting...")
        await connect(bot)
        print("✓ Connected\n")
        
        step = 0
        
        # PHASE 1: To menu selection
        print(f"\n{'═' * 80}")
        print(f"PHASE 1: Login → Menu Selection")
        print(f"{'═' * 80}")
        
        for attempt in range(15):
            step += 1
            try:
                input_type, prompt_id, screen, kv_data = await wait_and_respond(
                    bot, timeout_ms=8000
                )
            except TimeoutError:
                print(f"\n❌ TIMEOUT - no prompt for 8 seconds")
                return
            except RuntimeError as e:
                print(f"\n❌ ERROR: {e}")
                if "Stuck in loop" in str(e):
                    print(f"\nStuck in loop analysis:")
                    print(f"  Last prompt seen repeatedly: {prompt_id}")
                    print(f"  This means the bot is sending the same thing and getting same prompt")
                    print(f"  Check: Is send_input() being called? Is \\r being added?")
                return
            
            await show_step(step, screen, prompt_id, input_type)
            
            # Handle prompts - USE send_input() FOR MULTI_KEY!
            if "login_name" in prompt_id:
                print(f"\n→ Sending username using send_input() with \\r newline")
                await send_input(bot, "testbot", input_type)
            
            elif "menu_selection" in prompt_id:
                print(f"\n✓ REACHED MENU SELECTION - Success!")
                break
            
            elif input_type == "any_key":
                print(f"\n→ Sending space")
                await send_input(bot, " ", input_type)
            
            else:
                print(f"\n→ Sending space")
                await send_input(bot, " ", input_type)
        
        # PHASE 2: Game selection
        print(f"\n{'═' * 80}")
        print(f"PHASE 2: Send Game Selection")
        print(f"{'═' * 80}")
        print(f"→ Sending 'B' to select game")
        await bot.session.send("B")
        await asyncio.sleep(0.5)
        
        # PHASE 3: Game load
        print(f"\n{'═' * 80}")
        print(f"PHASE 3: Game Loading (showing every 10th step)")
        print(f"{'═' * 80}")
        
        pause_count = 0
        
        for attempt in range(70):
            step += 1
            try:
                input_type, prompt_id, screen, kv_data = await wait_and_respond(
                    bot, timeout_ms=20000
                )
            except TimeoutError:
                print(f"\n❌ TIMEOUT - game load exceeded 20 seconds")
                return
            except RuntimeError as e:
                print(f"\n❌ ERROR: {e}")
                return
            
            # Skip repetitive pause screens
            if "pause" in prompt_id:
                pause_count += 1
                if pause_count % 10 != 1:
                    await bot.session.send(" ")
                    await asyncio.sleep(0.2)
                    continue
            
            await show_step(step, screen, prompt_id, input_type)
            
            # Handle
            if "password" in prompt_id:
                print(f"\n→ Sending game password")
                await send_input(bot, "game", input_type)
            
            elif "command" in prompt_id or "sector" in prompt_id:
                print(f"\n{'✓' * 40}")
                print(f"✓ LOGIN COMPLETE - Reached command prompt!")
                print(f"✓ Successfully navigated all login phases!")
                print(f"{'✓' * 40}\n")
                return
            
            elif input_type == "any_key":
                await send_input(bot, " ", input_type)
            
            else:
                await send_input(bot, " ", input_type)
        
        print(f"\n❌ Did not reach command prompt")
        
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
