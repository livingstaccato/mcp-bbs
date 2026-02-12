# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Screen parsing utilities for trading operations."""

from __future__ import annotations

import re

from bbsbot.logging import get_logger

logger = get_logger(__name__)


_SECTOR_BRACKET_RE = re.compile(r"\[(\d+)\]\s*\(\?")
_SECTOR_WORD_RE = re.compile(r"\bsector\s+(\d+)\b", re.IGNORECASE)


def extract_sector_from_screen(screen: str) -> int | None:
    """Extract sector number from screen text.

    Tries bracket format first, then word format.

    Args:
        screen: Screen text to parse

    Returns:
        Sector number (1-1000) or None if not found
    """
    matches = _SECTOR_BRACKET_RE.findall(screen)
    if matches:
        return int(matches[-1])
    matches = _SECTOR_WORD_RE.findall(screen)
    if matches:
        return int(matches[-1])
    return None
