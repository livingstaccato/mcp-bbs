"""Compact status display for goal progress.

Renders single-line status displays for real-time updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.games.tw2002.visualization.colors import (
    STATUS_ICONS,
    Colors,
    Icons,
    colorize,
    get_goal_color,
)

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import GoalPhase


class GoalStatusDisplay:
    """Renders compact single-line status displays."""

    def render_compact(
        self,
        phase: GoalPhase,
        current_turn: int,
        max_turns: int,
    ) -> str:
        """Render compact one-line status.

        Args:
            phase: Current goal phase
            current_turn: Current turn number
            max_turns: Maximum turns

        Returns:
            Compact status line
        """
        # Turn counter
        turn_str = colorize(f"[T{current_turn}/{max_turns}]", Colors.FG_GRAY)

        # Mini progress bar (20 chars)
        if max_turns > 0:
            progress = int((current_turn / max_turns) * 20)
        else:
            progress = min(10, current_turn // max(1, current_turn))  # Fallback: show partial bar
        bar = Icons.BLOCK_LIGHT * progress + Icons.BLOCK_PENDING * (20 - progress)
        bar_colored = colorize(bar, get_goal_color(phase.goal_id))

        # Goal name and status
        goal_color = get_goal_color(phase.goal_id)
        status_icon = STATUS_ICONS.get(phase.status, Icons.ACTIVE)
        goal_str = colorize(f"{status_icon} {phase.goal_id.upper()}", goal_color, bold=True)

        # Metrics
        metrics_parts = []
        if "start_credits" in phase.metrics and "end_credits" in phase.metrics:
            profit = phase.metrics.get("end_credits", 0) - phase.metrics.get("start_credits", 0)
            if profit > 0:
                metrics_parts.append(colorize(f"+{profit:,}cr", Colors.FG_GREEN))
            elif profit < 0:
                metrics_parts.append(colorize(f"{profit:,}cr", Colors.FG_RED))

        metrics_str = " | ".join(metrics_parts) if metrics_parts else ""

        return f"{turn_str} {bar_colored} {goal_str} {metrics_str}".strip()
