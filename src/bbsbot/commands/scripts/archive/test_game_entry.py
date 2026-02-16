#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Wrapper for TW2002 game entry verification."""

import asyncio

from bbsbot.games.tw2002.verification.game_entry import main

if __name__ == "__main__":
    asyncio.run(main())
