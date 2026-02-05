#!/usr/bin/env python3
"""Wrapper for TW2002 TWGS command verification."""

import asyncio
from bbsbot.game.tw2002.verification.twgs_commands import main


if __name__ == "__main__":
    asyncio.run(main())
