"""Timeline visualization for goal phases.

Renders horizontal progress bars showing goal progression over turns.
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

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import GoalPhase


class GoalTimeline:
    """Renders ASCII timeline visualization of goal phases."""

    def __init__(
        self,
        phases: list[GoalPhase],
        current_turn: int,
        max_turns: int,
        width: int = 76,
    ):
        """Initialize timeline renderer.

        Args:
            phases: List of goal phases to visualize
            current_turn: Current turn number
            max_turns: Maximum turns in session
            width: Width of timeline bar in characters
        """
        self.phases = phases
        self.current_turn = current_turn
        self.max_turns = max_turns
        self.width = width

    def render_progress_bar(self) -> str:
        """Render horizontal progress bar with goal segments.

        Returns:
            Multi-line ASCII progress bar
        """
        if not self.phases:
            return self._render_empty_bar()

        lines = []
        lines.append("┌" + "─" * self.width + "┐")

        # Build segments
        segments = self._build_segments()
        bar_line = "│" + segments + "│"
        lines.append(bar_line)

        # Add goal labels
        label_line = self._build_label_line()
        lines.append("│" + label_line + "│")

        # Add metrics line
        metrics_line = self._build_metrics_line()
        lines.append("│" + metrics_line + "│")

        lines.append("└" + "─" * self.width + "┘")

        # Add current position marker
        marker_line = self._build_marker_line()
        if marker_line:
            lines.append(marker_line)

        return "\n".join(lines)

    def _render_empty_bar(self) -> str:
        """Render empty progress bar.

        Returns:
            Empty bar visualization
        """
        lines = []
        lines.append("┌" + "─" * self.width + "┐")
        lines.append("│" + " " * self.width + "│")
        lines.append("│" + colorize("No goal phases yet", Colors.FG_GRAY).center(self.width + 10) + "│")
        lines.append("│" + " " * self.width + "│")
        lines.append("└" + "─" * self.width + "┘")
        return "\n".join(lines)

    def _build_segments(self) -> str:
        """Build the progress bar segments.

        Returns:
            String of colored block characters
        """
        segments = []
        for phase in self.phases:
            start = phase.start_turn
            end = phase.end_turn if phase.end_turn is not None else self.current_turn

            # Calculate segment width
            phase_duration = end - start + 1
            segment_width = int((phase_duration / self.max_turns) * self.width)
            segment_width = max(1, segment_width)  # At least 1 char

            # Choose character based on status
            match phase.status:
                case "completed":
                    char = Icons.BLOCK_FULL
                case "active":
                    char = Icons.BLOCK_LIGHT
                case "failed" | "rewound":
                    char = Icons.WARNING
                case _:
                    char = Icons.BLOCK_PENDING

            # Colorize segment
            color = get_goal_color(phase.goal_id)
            segment = colorize(char * segment_width, color)
            segments.append(segment)

        # Pad to width
        total_chars = sum(
            int(((p.end_turn if p.end_turn else self.current_turn) - p.start_turn + 1) / self.max_turns * self.width)
            for p in self.phases
        )
        total_chars = max(1, total_chars)

        remaining = self.width - total_chars
        if remaining > 0:
            segments.append(colorize(Icons.BLOCK_PENDING * remaining, Colors.FG_GRAY))

        return "".join(segments)

    def _build_label_line(self) -> str:
        """Build goal name labels line.

        Returns:
            Labeled line with goal names
        """
        labels = []
        for phase in self.phases:
            start = phase.start_turn
            end = phase.end_turn if phase.end_turn is not None else self.current_turn
            phase_duration = end - start + 1
            segment_width = int((phase_duration / self.max_turns) * self.width)
            segment_width = max(1, segment_width)

            # Format label
            label = f"{phase.goal_id.upper()[:segment_width]}"
            color = get_goal_color(phase.goal_id)
            labels.append(colorize(label.center(segment_width), color, bold=True))

        # Pad
        total_chars = sum(
            int(((p.end_turn if p.end_turn else self.current_turn) - p.start_turn + 1) / self.max_turns * self.width)
            for p in self.phases
        )
        remaining = self.width - total_chars
        if remaining > 0:
            labels.append(" " * remaining)

        return "".join(labels)

    def _build_metrics_line(self) -> str:
        """Build metrics line showing key stats for each phase.

        Returns:
            Metrics line
        """
        metrics = []
        for phase in self.phases:
            start = phase.start_turn
            end = phase.end_turn if phase.end_turn is not None else self.current_turn
            phase_duration = end - start + 1
            segment_width = int((phase_duration / self.max_turns) * self.width)
            segment_width = max(1, segment_width)

            # Format metric
            icon = STATUS_ICONS.get(phase.status, Icons.ACTIVE)
            color = STATUS_COLORS.get(phase.status, Colors.FG_WHITE)

            # Show turn range
            metric = f"{icon} {start}-{end}"
            if len(metric) > segment_width:
                metric = icon

            metrics.append(colorize(metric.center(segment_width), color))

        # Pad
        total_chars = sum(
            int(((p.end_turn if p.end_turn else self.current_turn) - p.start_turn + 1) / self.max_turns * self.width)
            for p in self.phases
        )
        remaining = self.width - total_chars
        if remaining > 0:
            metrics.append(" " * remaining)

        return "".join(metrics)

    def _build_marker_line(self) -> str:
        """Build current position marker line.

        Returns:
            Marker line showing current turn position
        """
        if self.current_turn <= 0 or self.current_turn > self.max_turns:
            return ""

        # Calculate marker position
        marker_pos = int((self.current_turn / self.max_turns) * self.width)
        marker_pos = max(0, min(marker_pos, self.width - 1))

        # Build marker line
        line = " " * (marker_pos + 1)  # +1 for border
        line += colorize(f"{Icons.ARROW_UP} Turn {self.current_turn}", Colors.FG_CYAN, bold=True)
        return line

    def render_legend(self) -> str:
        """Render legend explaining symbols.

        Returns:
            Legend text
        """
        legend_parts = [
            colorize(f"{Icons.BLOCK_FULL}", Colors.FG_GREEN) + " Completed",
            colorize(f"{Icons.BLOCK_LIGHT}", Colors.FG_CYAN) + " Active",
            colorize(f"{Icons.WARNING}", Colors.FG_RED) + " Failed/Rewound",
            colorize(f"{Icons.BLOCK_PENDING}", Colors.FG_GRAY) + " Pending",
        ]
        return "Legend: " + " | ".join(legend_parts)
