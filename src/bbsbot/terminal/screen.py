# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Screen parsing utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyte


def parse_screen_text(screen: pyte.Screen) -> str:
    """Parse screen display into text string.

    Args:
        screen: Pyte screen object

    Returns:
        Screen text with lines joined by newlines
    """
    return "\n".join(screen.display)
