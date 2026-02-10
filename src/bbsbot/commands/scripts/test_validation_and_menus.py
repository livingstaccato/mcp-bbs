#!/usr/bin/env python3
"""Wrapper for TW2002 validation/menu verification."""

import asyncio
import sys

from bbsbot.games.tw2002.verification.validation_and_menus import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
