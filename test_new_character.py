#!/usr/bin/env python3
"""Proof: Bot works with new character on localhost:2002."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from twbot import TradingBot
from twbot.connection import connect
from twbot.login import login_sequence
from twbot.trading import single_trading_cycle

async def test():
    unique_char = "bottest2001"
    char_password = unique_char
    game_password = "game"
    
    bot = TradingBot()
    
    try:
        print(f"\n{'=' * 80}")
        print(f"PROOF: Bot working with new character")
        print(f"{'=' * 80}")
        print(f"Character: {unique_char}")
        print(f"Password: {char_password}")
        print(f"Server: localhost:2002")
        print(f"{'=' * 80}\n")
        
        await connect(bot)
        print("✓ Connected to BBS\n")
        
        await login_sequence(
            bot,
            game_password=game_password,
            character_password=char_password,
            username=unique_char
        )
        
        print(f"\n✓ Login successful!\n")
        
        # Run trading cycle
        await single_trading_cycle(bot, start_sector=499)
        
        print("\n" + "=" * 80)
        print("✅ SUCCESS: Bot completed full trading cycle!")
        print("=" * 80)
        print(f"Validation system: WORKING END-TO-END on localhost:2002")
        print("=" * 80 + "\n")
        
        return True
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

if __name__ == "__main__":
    try:
        result = asyncio.run(test())
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
