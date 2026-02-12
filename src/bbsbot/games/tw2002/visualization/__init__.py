# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Goal progress visualization package.

Provides rich terminal visualizations for TW2002 bot goal tracking with
xterm-256color support.
"""

from __future__ import annotations

from bbsbot.games.tw2002.visualization.colors import (
    Colors,
    Icons,
    colorize,
    get_goal_color,
)
from bbsbot.games.tw2002.visualization.status import GoalStatusDisplay
from bbsbot.games.tw2002.visualization.summary import GoalSummaryReport
from bbsbot.games.tw2002.visualization.timeline import GoalTimeline

__all__ = [
    "Colors",
    "Icons",
    "colorize",
    "get_goal_color",
    "GoalTimeline",
    "GoalStatusDisplay",
    "GoalSummaryReport",
]
