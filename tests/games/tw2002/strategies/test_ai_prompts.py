# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AI strategy prompt builder."""

import pytest

from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
from bbsbot.games.tw2002.strategies.ai.prompts import PromptBuilder


@pytest.fixture
def prompt_builder():
    """Create prompt builder."""
    return PromptBuilder()


@pytest.fixture
def game_state():
    """Create test game state."""
    return GameState(
        context="sector_command",
        sector=1,
        credits=10000,
        turns_left=100,
        has_port=True,
        port_class="BBS",
        warps=[2, 3, 4],
        holds_total=50,
        holds_free=40,
        fighters=10,
        shields=100,
    )


@pytest.fixture
def sector_knowledge():
    """Create sector knowledge."""
    knowledge = SectorKnowledge()
    # Add some known sectors
    knowledge.update_sector(2, {"port_class": "SSB"})
    knowledge.update_sector(3, {"port_class": "BSS"})
    return knowledge


@pytest.fixture
def stats():
    """Create strategy stats."""
    return {
        "trades_executed": 5,
        "total_profit": 5000,
        "profit_per_turn": 50.0,
        "turns_used": 100,
    }


def test_prompt_builder_builds_messages(prompt_builder, game_state, sector_knowledge, stats):
    """Test building chat messages."""
    messages = prompt_builder.build(game_state, sector_knowledge, stats)

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[1].role == "user"

    # System prompt should contain game mechanics
    assert "Trade Wars 2002" in messages[0].content
    assert "TRADE" in messages[0].content
    assert "MOVE" in messages[0].content

    # User prompt should contain game state
    assert "Sector 1" in messages[1].content
    assert "10000" in messages[1].content  # credits
    assert "100" in messages[1].content  # turns


def test_prompt_builder_includes_adjacent_sectors(prompt_builder, game_state, sector_knowledge, stats):
    """Test including adjacent sector info."""
    messages = prompt_builder.build(game_state, sector_knowledge, stats)
    user_prompt = messages[1].content

    # Should include known adjacent sectors
    assert "Sector 2" in user_prompt or "Adjacent" in user_prompt
    assert "Port SSB" in user_prompt or "SSB" in user_prompt


def test_prompt_builder_formats_current_situation(prompt_builder, game_state):
    """Test formatting current situation."""
    text = prompt_builder._format_current_situation(game_state)

    assert "Sector 1" in text
    assert "sector_command" in text
    assert "10000" in text
    assert "100" in text


def test_prompt_builder_formats_ship_status(prompt_builder, game_state):
    """Test formatting ship status."""
    text = prompt_builder._format_ship_status(game_state)

    assert "40/50" in text  # holds
    assert "10" in text  # fighters
    assert "100" in text  # shields


def test_prompt_builder_formats_current_sector(prompt_builder, game_state):
    """Test formatting current sector."""
    text = prompt_builder._format_current_sector(game_state)

    assert "True" in text  # has port
    assert "BBS" in text
    assert "2, 3, 4" in text  # warps


def test_prompt_builder_formats_stats(prompt_builder, stats):
    """Test formatting stats."""
    text = prompt_builder._format_stats(stats)

    assert "5" in text  # trades
    assert "5000" in text  # profit
    assert "50.0" in text  # profit per turn
    assert "100" in text  # turns used
