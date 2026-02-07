#!/usr/bin/env python3
"""Wrapper for TW2002 orientation recovery verification."""

import asyncio
import sys
from bbsbot.games.tw2002.verification.orientation_recovery import main


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
