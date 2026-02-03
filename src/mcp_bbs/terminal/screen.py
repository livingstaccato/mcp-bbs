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
