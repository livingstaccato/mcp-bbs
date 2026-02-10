#!/usr/bin/env python3
"""Wrapper for TW2002 trading integration verification."""

import asyncio
import sys

from bbsbot.games.tw2002.verification.trading_integration import main

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
