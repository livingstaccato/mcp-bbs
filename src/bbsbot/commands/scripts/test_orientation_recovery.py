#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Wrapper for TW2002 orientation recovery verification."""

import asyncio
import sys

from bbsbot.games.tw2002.verification.orientation_recovery import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
