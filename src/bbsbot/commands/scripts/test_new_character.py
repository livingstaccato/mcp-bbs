#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Wrapper for TW2002 new character verification."""

import asyncio
import sys

from bbsbot.games.tw2002.verification.new_character import test

if __name__ == "__main__":
    try:
        result = asyncio.run(test())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
