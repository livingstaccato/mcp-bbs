"""Detailed session summary reports for goal progress.

Renders comprehensive reports with timelines, transition tables, and statistics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.games.tw2002.visualization.colors import (
    Colors,
    Icons,
    STATUS_COLORS,
    STATUS_ICONS,
    colorize,
    get_goal_color,
)
from bbsbot.games.tw2002.visualization.timeline import GoalTimeline

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import GoalPhase


class GoalSummaryReport:
    """Renders detailed session summary reports."""

    def __init__(self, phases: list[GoalPhase], max_turns: int):
        """Initialize summary reporter.

        Args:
            phases: List of goal phases
            max_turns: Maximum turns in session
        """
        self.phases = phases
        self.max_turns = max_turns

    def render_full_summary(self) -> str:
        """Render complete session summary.

        Returns:
            Multi-section summary report
        """
        lines = []

        # Header
        completed_turns = max(
            p.end_turn for p in self.phases if p.end_turn is not None
        ) if self.phases else 0

        header = f"GOAL SESSION SUMMARY - {completed_turns}/{self.max_turns} turns completed"
        lines.append("")
        lines.append("═" * 80)
        lines.append(colorize(header, Colors.FG_CYAN, bold=True).center(90))
        lines.append("═" * 80)
        lines.append("")

        # Timeline visualization
        lines.append(colorize("Timeline:", Colors.FG_WHITE, bold=True))
        timeline = GoalTimeline(self.phases, completed_turns, self.max_turns)
        lines.append(timeline.render_progress_bar())
        lines.append("")

        # Transition table
        lines.append(colorize("Goal Transitions:", Colors.FG_WHITE, bold=True))
        lines.append(self.render_transition_table())
        lines.append("")

        # Summary stats
        lines.append(colorize("Summary:", Colors.FG_WHITE, bold=True))
        lines.append(self._render_summary_stats())
        lines.append("")

        lines.append("═" * 80)

        return "\n".join(lines)

    def render_transition_table(self) -> str:
        """Render table of goal transitions.

        Returns:
            Formatted table
        """
        if not self.phases:
            return colorize("  No goal transitions recorded", Colors.FG_GRAY)

        lines = []

        # Header
        header = (
            f"  {'#':<3} {'Turns':<12} {'Goal':<14} {'Status':<10} "
            f"{'Type':<8} {'Reason':<30}"
        )
        lines.append(colorize(header, Colors.FG_WHITE, bold=True))
        lines.append("  " + "─" * 77)

        # Rows
        for idx, phase in enumerate(self.phases, 1):
            end = phase.end_turn if phase.end_turn is not None else "active"
            turn_range = f"{phase.start_turn:>3} - {str(end):<5}"

            status_icon = STATUS_ICONS.get(phase.status, Icons.ACTIVE)
            status_color = STATUS_COLORS.get(phase.status, Colors.FG_WHITE)
            status_str = colorize(f"{status_icon} {phase.status:<8}", status_color)

            goal_color = get_goal_color(phase.goal_id)
            goal_str = colorize(phase.goal_id.upper()[:12], goal_color)

            trigger_icon = "⚙" if phase.trigger_type == "auto" else "👤"
            trigger_str = f"{trigger_icon} {phase.trigger_type[:6]}"

            reason_str = phase.reason[:28] if phase.reason else ""

            row = f"  {idx:<3} {turn_range:<12} {goal_str:<14} {status_str:<10} {trigger_str:<8} {reason_str:<30}"
            lines.append(row)

        return "\n".join(lines)

    def _render_summary_stats(self) -> str:
        """Render summary statistics.

        Returns:
            Summary stats text
        """
        total_phases = len(self.phases)
        completed = len([p for p in self.phases if p.status == "completed"])
        failed = len([p for p in self.phases if p.status in ("failed", "rewound")])
        active = len([p for p in self.phases if p.status == "active"])

        lines = []
        lines.append(f"  Total goal phases: {total_phases}")
        lines.append(f"  {colorize(Icons.COMPLETED, Colors.FG_GREEN)} Completed: {completed}")
        if failed > 0:
            lines.append(f"  {colorize(Icons.WARNING, Colors.FG_RED)} Failed/Rewound: {failed}")
        if active > 0:
            lines.append(f"  {colorize(Icons.ACTIVE, Colors.FG_CYAN)} Active: {active}")

        return "\n".join(lines)
