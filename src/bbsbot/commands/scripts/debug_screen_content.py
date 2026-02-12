#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Capture full screen content after login."""

import asyncio

from bbsbot.games.tw2002 import TradingBot
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.io import wait_and_respond
from bbsbot.games.tw2002.login import login_sequence


async def test():
    bot = TradingBot()

    try:
        await connect(bot)
        await login_sequence(bot)

        # Get first prompt after login
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=5000)

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
