# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for goal progress visualization system."""

from __future__ import annotations

import pytest

from bbsbot.games.tw2002.config import GoalPhase
from bbsbot.games.tw2002.visualization import (
    GoalStatusDisplay,
    GoalSummaryReport,
    GoalTimeline,
    Icons,
)


@pytest.fixture
def sample_phases() -> list[GoalPhase]:
    """Create sample goal phases for testing."""
    return [
        GoalPhase(
            goal_id="profit",
            start_turn=1,
            end_turn=20,
            status="completed",
            trigger_type="auto",
            metrics={
                "start_credits": 10000,
                "end_credits": 35000,
            },
            reason="Low credits at start",
        ),
        GoalPhase(
            goal_id="combat",
            start_turn=21,
            end_turn=40,
            status="active",
            trigger_type="auto",
            metrics={
                "start_credits": 35000,
                "end_credits": 50000,
            },
            reason="High credits, need fighters",
        ),
    ]


@pytest.fixture
def phases_with_rewind() -> list[GoalPhase]:
    """Create goal phases with a rewind scenario."""
    return [
        GoalPhase(
            goal_id="combat",
            start_turn=1,
            end_turn=10,
            status="rewound",
            trigger_type="auto",
            metrics={
                "rewind_reason": "Ship destroyed in combat",
                "rewind_to_turn": 5,
            },
            reason="Initial combat attempt",
        ),
        GoalPhase(
            goal_id="combat",
            start_turn=5,
            end_turn=20,
            status="active",
            trigger_type="auto",
            metrics={},
            reason="Retry after rewind: Ship destroyed in combat",
        ),
    ]


class TestGoalTimeline:
    """Test GoalTimeline rendering."""

    def test_renders_progress_bar(self, sample_phases):
        """Test that progress bar renders correctly."""
        timeline = GoalTimeline(sample_phases, current_turn=30, max_turns=100)
        output = timeline.render_progress_bar()

        # Check structure
        assert "┌" in output
        assert "└" in output
        assert "│" in output

        # Check goal names appear
        assert "PROFIT" in output
        assert "COMBAT" in output

    def test_renders_empty_bar(self):
        """Test empty progress bar when no phases."""
        timeline = GoalTimeline([], current_turn=0, max_turns=100)
        output = timeline.render_progress_bar()

        assert "No goal phases yet" in output

    def test_shows_completed_segments(self, sample_phases):
        """Test completed segments use full blocks."""
        timeline = GoalTimeline(sample_phases, current_turn=30, max_turns=100)
        output = timeline.render_progress_bar()

        # Should contain block characters (checking for presence, not exact format due to ANSI)
        assert Icons.BLOCK_FULL in output or Icons.BLOCK_LIGHT in output

    def test_shows_rewind_markers(self, phases_with_rewind):
        """Test rewind indicators appear in visualization."""
        timeline = GoalTimeline(phases_with_rewind, current_turn=15, max_turns=100)
        output = timeline.render_progress_bar()

        # Should contain warning icon for rewound phase
        assert Icons.WARNING in output

    def test_renders_legend(self, sample_phases):
        """Test legend generation."""
        timeline = GoalTimeline(sample_phases, current_turn=30, max_turns=100)
        legend = timeline.render_legend()

        assert "Legend:" in legend
        assert "Completed" in legend
        assert "Active" in legend
        assert "Failed/Rewound" in legend
        assert "Pending" in legend

    def test_current_turn_marker(self, sample_phases):
        """Test current turn marker appears."""
        timeline = GoalTimeline(sample_phases, current_turn=30, max_turns=100)
        output = timeline.render_progress_bar()

        # Should show current turn
        assert "Turn 30" in output
        assert Icons.ARROW_UP in output


class TestGoalStatusDisplay:
    """Test compact status display."""

    def test_renders_compact_status(self, sample_phases):
        """Test single-line status format."""
        display = GoalStatusDisplay()
        phase = sample_phases[1]  # Active combat phase
        output = display.render_compact(phase, current_turn=30, max_turns=100)

        # Check components
        assert "30" in output  # Turn number
        assert "100" in output  # Max turns
        assert "COMBAT" in output  # Goal name
        assert Icons.ACTIVE in output  # Status icon

    def test_shows_profit_metrics(self, sample_phases):
        """Test profit metrics appear in status."""
        display = GoalStatusDisplay()
        phase = sample_phases[1]  # Has credits metrics
        output = display.render_compact(phase, current_turn=30, max_turns=100)

        # Should show profit (50000 - 35000 = +15000)
        assert "15,000" in output or "15000" in output
        assert "cr" in output

    def test_includes_progress_bar(self, sample_phases):
        """Test mini progress bar is included."""
        display = GoalStatusDisplay()
        phase = sample_phases[0]
        output = display.render_compact(phase, current_turn=30, max_turns=100)

        # Should contain block characters for progress
        assert Icons.BLOCK_LIGHT in output or Icons.BLOCK_PENDING in output


class TestGoalSummaryReport:
    """Test detailed summary reports."""

    def test_renders_full_summary(self, sample_phases):
        """Test complete summary report generation."""
        report = GoalSummaryReport(sample_phases, max_turns=100)
        output = report.render_full_summary()

        # Check sections
        assert "GOAL SESSION SUMMARY" in output
        assert "Timeline:" in output
        assert "Goal Transitions:" in output
        assert "Summary:" in output

        # Check goals appear
        assert "PROFIT" in output or "profit" in output.lower()
        assert "COMBAT" in output or "combat" in output.lower()

    def test_renders_transition_table(self, sample_phases):
        """Test transition table formatting."""
        report = GoalSummaryReport(sample_phases, max_turns=100)
        table = report.render_transition_table()

        # Check table structure
        assert "#" in table
        assert "Turns" in table
        assert "Goal" in table
        assert "Status" in table
        assert "Type" in table

        # Check data appears
        assert "1" in table  # Phase 1
        assert "2" in table  # Phase 2
        assert Icons.COMPLETED in table  # Completed status
        assert Icons.ACTIVE in table  # Active status

    def test_shows_rewind_in_table(self, phases_with_rewind):
        """Test rewind phases appear in transition table."""
        report = GoalSummaryReport(phases_with_rewind, max_turns=100)
        table = report.render_transition_table()

        # Check rewind indicator
        assert Icons.REWOUND in table

    def test_summary_stats(self, sample_phases):
        """Test summary statistics calculation."""
        report = GoalSummaryReport(sample_phases, max_turns=100)
        output = report.render_full_summary()

        # Check stats appear
        assert "Total goal phases: 2" in output
        assert "Completed: 1" in output
        assert "Active: 1" in output

    def test_empty_phases_message(self):
        """Test message when no phases exist."""
        report = GoalSummaryReport([], max_turns=100)
        table = report.render_transition_table()

        assert "No goal transitions recorded" in table


class TestVisualizationIntegration:
    """Integration tests for visualization with AIStrategy."""

    def test_phases_track_during_goal_changes(self):
        """Test that phases are created when goals change."""
        from bbsbot.games.tw2002.config import BotConfig
        from bbsbot.games.tw2002.orientation import SectorKnowledge
        from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy

        config = BotConfig()
        knowledge = SectorKnowledge()
        strategy = AIStrategy(config, knowledge)

        # Should have initial phase
        assert len(strategy._goal_phases) == 1
        assert strategy._goal_phases[0].goal_id == strategy._current_goal_id
        assert strategy._goal_phases[0].status == "active"

    def test_timeline_renders_with_strategy_phases(self):
        """Test timeline renders correctly with real strategy phases."""
        from bbsbot.games.tw2002.config import BotConfig
        from bbsbot.games.tw2002.orientation import SectorKnowledge
        from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy

        config = BotConfig()
        knowledge = SectorKnowledge()
        strategy = AIStrategy(config, knowledge)

        # Create timeline
        timeline = GoalTimeline(
            phases=strategy._goal_phases,
            current_turn=strategy._current_turn,
            max_turns=strategy._max_turns,
        )

        # Should render without error
        output = timeline.render_progress_bar()
        assert output
        assert "┌" in output
        assert "└" in output

    def test_manual_goal_change_creates_phase(self):
        """Test setting goal manually creates new phase."""
        from bbsbot.games.tw2002.config import BotConfig
        from bbsbot.games.tw2002.orientation import SectorKnowledge
        from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy

        config = BotConfig()
        knowledge = SectorKnowledge()
        strategy = AIStrategy(config, knowledge)

        initial_phase_count = len(strategy._goal_phases)

        # Set new goal manually
        strategy.set_goal("combat", duration_turns=10)

        # Should have new phase
        assert len(strategy._goal_phases) > initial_phase_count
        assert strategy._goal_phases[-1].goal_id == "combat"
        assert strategy._goal_phases[-1].trigger_type == "manual"


class TestColorization:
    """Test color and formatting utilities."""

    def test_colorize_applies_color(self):
        """Test that colorize adds ANSI codes."""
        from bbsbot.games.tw2002.visualization import Colors, colorize

        result = colorize("test", Colors.FG_GREEN)

        # Should contain ANSI escape codes
        assert "\033[" in result
        assert "test" in result

    def test_get_goal_color(self):
        """Test goal-specific color mapping."""
        from bbsbot.games.tw2002.visualization import get_goal_color

        # Check known goals have colors
        assert get_goal_color("profit")
        assert get_goal_color("combat")
        assert get_goal_color("exploration")
        assert get_goal_color("banking")

        # Unknown goal should get default
        assert get_goal_color("unknown")
