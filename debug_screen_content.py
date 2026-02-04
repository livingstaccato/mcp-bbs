#!/usr/bin/env python3
"""Capture full screen content after login."""

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
        await login_sequence(bot)
        
        # Get first prompt after login
        input_type, prompt_id, screen, kv_data = await wait_and_respond(
            bot, timeout_ms=5000
        )
        
        print("=== FULL SCREEN AFTER LOGIN ===\n")
        print(screen)
        print(f"\n=== PROMPT ID: {prompt_id} ===\n")
        print(f"Input type: {input_type}")
        print(f"K/V data: {kv_data}")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

if __name__ == "__main__":
    asyncio.run(test())
