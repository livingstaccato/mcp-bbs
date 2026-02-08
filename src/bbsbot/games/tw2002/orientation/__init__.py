"""Orientation system for TW2002 bot.

Three-layer approach:
1. Safety - Reach a known stable state
2. Context - Gather comprehensive game state
3. Navigation - Plan routes using knowledge

Usage:
    state = await bot.orient()  # Returns GameState
"""

from __future__ import annotations

# Re-export public APIs
from .models import GameState, OrientationError, SectorInfo, QuickState
from .knowledge import SectorKnowledge
from .detection import (
    where_am_i,
    recover_to_safe_state,
    detect_context,
    SAFE_CONTEXTS,
    ACTION_CONTEXTS,
    DANGER_CONTEXTS,
    INFO_CONTEXTS,
    TRANSITION_CONTEXTS,
    NAVIGATION_CONTEXTS,
)
from .layers import orient
from .parsing import parse_display_screen, parse_sector_display

__all__ = [
    # Core models
    "GameState",
    "OrientationError",
    "SectorInfo",
    "QuickState",
    # Knowledge system
    "SectorKnowledge",
    # Detection functions
    "where_am_i",
    "recover_to_safe_state",
    "detect_context",
    # Main entry point
    "orient",
    # Parsing functions
    "parse_display_screen",
    "parse_sector_display",
    # Context constants
    "SAFE_CONTEXTS",
    "ACTION_CONTEXTS",
    "DANGER_CONTEXTS",
    "INFO_CONTEXTS",
    "TRANSITION_CONTEXTS",
    "NAVIGATION_CONTEXTS",
]
