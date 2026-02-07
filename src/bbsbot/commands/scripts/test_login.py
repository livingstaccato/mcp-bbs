#!/usr/bin/env python3
"""Wrapper for TW2002 login verification."""

import asyncio
from bbsbot.games.tw2002.verification.login import login


if __name__ == "__main__":
    asyncio.run(login())
