#!/usr/bin/env python3
"""Wrapper for TW2002 game entry verification."""

import asyncio
from bbsbot.game.tw2002.verification.game_entry import main


if __name__ == "__main__":
    asyncio.run(main())
