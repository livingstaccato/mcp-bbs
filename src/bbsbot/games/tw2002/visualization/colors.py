"""Color definitions and utilities for xterm-256color terminal output.

Provides ANSI escape codes and colorization utilities for rich terminal
visualizations with 256-color support.
"""

from __future__ import annotations


# ANSI color codes for xterm-256color
class Colors:
    """ANSI escape codes for 256-color terminal support."""

    # Reset
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors (bright versions)
    FG_BLACK = "\033[38;5;0m"
    FG_RED = "\033[38;5;196m"
    FG_GREEN = "\033[38;5;46m"
    FG_YELLOW = "\033[38;5;226m"
    FG_BLUE = "\033[38;5;33m"
    FG_MAGENTA = "\033[38;5;201m"
    FG_CYAN = "\033[38;5;51m"
    FG_WHITE = "\033[38;5;231m"
    FG_ORANGE = "\033[38;5;208m"
    FG_GRAY = "\033[38;5;244m"

    # Background colors
    BG_BLACK = "\033[48;5;0m"
    BG_RED = "\033[48;5;196m"
    BG_GREEN = "\033[48;5;46m"
    BG_YELLOW = "\033[48;5;226m"
    BG_BLUE = "\033[48;5;33m"
    BG_MAGENTA = "\033[48;5;201m"
    BG_CYAN = "\033[48;5;51m"
    BG_WHITE = "\033[48;5;231m"
    BG_DARK_GRAY = "\033[48;5;236m"
    BG_LIGHT_GRAY = "\033[48;5;250m"

    # Goal-specific colors
    PROFIT_COLOR = "\033[38;5;46m"  # Bright green
    COMBAT_COLOR = "\033[38;5;196m"  # Bright red
    EXPLORATION_COLOR = "\033[38;5;51m"  # Bright cyan
    BANKING_COLOR = "\033[38;5;226m"  # Bright yellow


# Status icons and block characters
class Icons:
    """Unicode characters for status indicators and progress bars."""

    # Status indicators
    ACTIVE = "●"
    COMPLETED = "✓"
    FAILED = "✗"
    REWOUND = "↻"
    WARNING = "⚠"

    # Progress bar characters
    BLOCK_FULL = "█"
    BLOCK_LIGHT = "░"
    BLOCK_MEDIUM = "▒"
    BLOCK_DARK = "▓"
    BLOCK_PENDING = "─"

    # Arrows and markers
    ARROW_UP = "↑"
    ARROW_DOWN = "↓"
    ARROW_RIGHT = "→"
    ARROW_LEFT = "←"
    MARKER = "▶"


# Goal color mapping
GOAL_COLORS = {
    "profit": Colors.PROFIT_COLOR,
    "combat": Colors.COMBAT_COLOR,
    "exploration": Colors.EXPLORATION_COLOR,
    "banking": Colors.BANKING_COLOR,
}

# Status color mapping
STATUS_COLORS = {
    "active": Colors.FG_CYAN,
    "completed": Colors.FG_GREEN,
    "failed": Colors.FG_RED,
    "rewound": Colors.FG_YELLOW,
}

# Status icon mapping
STATUS_ICONS = {
    "active": Icons.ACTIVE,
    "completed": Icons.COMPLETED,
    "failed": Icons.FAILED,
    "rewound": Icons.REWOUND,
}


def colorize(text: str, color: str, bold: bool = False) -> str:
    """Apply ANSI color to text.

    Args:
        text: Text to colorize
        color: ANSI color code
        bold: Whether to make text bold

    Returns:
        Colorized text with ANSI codes
    """
    prefix = f"{Colors.BOLD}{color}" if bold else color
    return f"{prefix}{text}{Colors.RESET}"


def get_goal_color(goal_id: str) -> str:
    """Get color for a goal ID.

    Args:
        goal_id: Goal identifier

    Returns:
        ANSI color code
    """
    return GOAL_COLORS.get(goal_id.lower(), Colors.FG_WHITE)
