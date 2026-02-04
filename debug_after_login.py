#!/usr/bin/env python3
"""Debug what happens immediately after login."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from twbot import TradingBot
from twbot.connection import connect
from twbot.login import login_sequence
from twbot.io import wait_and_respond

async def test():
    bot = TradingBot()
    
    try:
        await connect(bot)
        print("✓ Connected\n")
        
        # Login
        print("Logging in...")
        await login_sequence(bot)
        print("✓ Logged in\n")
        
        # Now inspect the next 5 prompts without doing anything special
        print("Reading next 5 prompts from command line:\n")
        for i in range(5):
            try:
                input_type, prompt_id, screen, kv_data = await wait_and_respond(
                    bot, timeout_ms=5000
                )
                print(f"[{i+1}] {prompt_id} ({input_type})")
                print(f"    Screen excerpt: {screen[:100]}...")
                print()
            except TimeoutError:
                print(f"[{i+1}] TIMEOUT")
                break
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

if __name__ == "__main__":
    asyncio.run(test())
