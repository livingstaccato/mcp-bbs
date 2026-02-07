"""Tests for AI strategy response parser."""

import pytest

from bbsbot.games.tw2002.orientation import GameState
from bbsbot.games.tw2002.strategies.ai.parser import ResponseParser
from bbsbot.games.tw2002.strategies.base import TradeAction
from bbsbot.llm.types import ChatMessage, ChatResponse


@pytest.fixture
def parser():
    """Create response parser."""
    return ResponseParser()


@pytest.fixture
def game_state():
    """Create test game state."""
    return GameState(
        context="sector_command",
        sector=1,
        has_port=True,
        warps=[2, 3, 4],
    )


def test_parser_json_response(parser, game_state):
    """Test parsing JSON response."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content='{"action": "TRADE", "reasoning": "Good opportunity", "parameters": {"commodity": "fuel_ore"}}',
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.TRADE
    assert params["commodity"] == "fuel_ore"


def test_parser_json_in_markdown(parser, game_state):
    """Test parsing JSON wrapped in markdown."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content='```json\n{"action": "MOVE", "parameters": {"target_sector": 2}}\n```',
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.MOVE
    assert params["target_sector"] == 2


def test_parser_regex_fallback_trade(parser, game_state):
    """Test regex fallback for TRADE action."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="I recommend we TRADE fuel ore at this port.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.TRADE
    assert params.get("commodity") == "fuel_ore"


def test_parser_regex_fallback_move(parser, game_state):
    """Test regex fallback for MOVE action."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="We should MOVE to sector 3 next.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.MOVE
    assert params["target_sector"] == 3


def test_parser_regex_fallback_explore(parser, game_state):
    """Test regex fallback for EXPLORE action."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="Let's EXPLORE unknown sectors.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.EXPLORE


def test_parser_regex_fallback_bank(parser, game_state):
    """Test regex fallback for BANK action."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="We should BANK our credits now.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.BANK


def test_parser_regex_fallback_upgrade(parser, game_state):
    """Test regex fallback for UPGRADE action."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="Let's UPGRADE our fighters.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.UPGRADE
    assert params["upgrade_type"] == "fighters"


def test_parser_regex_fallback_retreat(parser, game_state):
    """Test regex fallback for RETREAT action."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="We need to RETREAT from this danger.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.RETREAT


def test_parser_regex_fallback_wait(parser, game_state):
    """Test regex fallback for WAIT action."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="Let's WAIT for now.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.WAIT


def test_parser_regex_fallback_done(parser, game_state):
    """Test regex fallback for DONE action."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="We're DONE playing for today.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.DONE


def test_parser_no_match_defaults_to_wait(parser, game_state):
    """Test that unmatched responses default to WAIT."""
    response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="I'm not sure what to do here.",
        ),
        model="llama2",
    )

    action, params = parser.parse(response, game_state)

    assert action == TradeAction.WAIT
