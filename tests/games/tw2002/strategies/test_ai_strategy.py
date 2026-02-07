"""Tests for AI strategy."""

import pytest
from unittest.mock import AsyncMock, patch

from bbsbot.games.tw2002.config import AIStrategyConfig, BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
from bbsbot.games.tw2002.strategies.base import TradeAction
from bbsbot.llm.types import ChatMessage, ChatResponse


@pytest.fixture
def bot_config():
    """Create test bot config."""
    config = BotConfig()
    config.trading.strategy = "ai_strategy"
    config.trading.ai_strategy = AIStrategyConfig(
        enabled=True,
        fallback_threshold=3,
        fallback_duration_turns=10,
    )
    return config


@pytest.fixture
def sector_knowledge():
    """Create test sector knowledge."""
    return SectorKnowledge()


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
def ai_strategy(bot_config, sector_knowledge):
    """Create AI strategy for testing."""
    return AIStrategy(bot_config, sector_knowledge)


def test_ai_strategy_init(ai_strategy):
    """Test AI strategy initialization."""
    assert ai_strategy.name == "ai_strategy"
    assert ai_strategy.consecutive_failures == 0
    assert ai_strategy.llm_manager is not None
    assert ai_strategy.prompt_builder is not None
    assert ai_strategy.parser is not None
    assert ai_strategy.fallback is not None


@pytest.mark.asyncio
async def test_ai_strategy_successful_decision(ai_strategy, game_state):
    """Test successful LLM decision."""
    # Mock LLM response
    mock_response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content='{"action": "TRADE", "reasoning": "Good opportunity", "confidence": 0.9, "parameters": {"commodity": "fuel_ore"}}',
        ),
        model="llama2",
    )

    with patch.object(ai_strategy.llm_manager, "chat", return_value=mock_response):
        action, params = await ai_strategy._get_next_action_async(game_state)

        assert action == TradeAction.TRADE
        assert params.get("commodity") == "fuel_ore"
        assert ai_strategy.consecutive_failures == 0


@pytest.mark.asyncio
async def test_ai_strategy_fallback_on_failure(ai_strategy, game_state):
    """Test fallback activation on failures."""
    # Simulate LLM failures
    with patch.object(ai_strategy.llm_manager, "chat", side_effect=Exception("LLM error")):
        # First failure
        action1, _ = await ai_strategy._get_next_action_async(game_state)
        assert ai_strategy.consecutive_failures == 1

        # Second failure
        action2, _ = await ai_strategy._get_next_action_async(game_state)
        assert ai_strategy.consecutive_failures == 2

        # Third failure - should enter fallback mode
        action3, _ = await ai_strategy._get_next_action_async(game_state)
        assert ai_strategy.consecutive_failures == 3
        assert ai_strategy.fallback_until_turn > 0

        # Fourth attempt - should use fallback
        action4, _ = await ai_strategy._get_next_action_async(game_state)
        # Fallback returns a valid action
        assert action4 is not None


@pytest.mark.asyncio
async def test_ai_strategy_logs_llm_decision(ai_strategy, game_state):
    mock_response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content='{"action": "TRADE", "reasoning": "Good opportunity", "confidence": 0.9, "parameters": {"commodity": "fuel_ore"}}',
        ),
        model="llama2",
    )

    mock_session_logger = AsyncMock()
    ai_strategy.set_session_logger(mock_session_logger)

    with patch.object(ai_strategy.llm_manager, "chat", return_value=mock_response):
        action, params = await ai_strategy._get_next_action_async(game_state)
        assert action == TradeAction.TRADE
        assert params.get("commodity") == "fuel_ore"

    # Ensure decision log was written.
    calls = [c for c in mock_session_logger.log_event.call_args_list if c.args and c.args[0] == "llm.decision"]
    assert calls, "Expected at least one llm.decision event"
    payload = calls[-1].args[1]
    assert payload["parsed"]["action"] == "TRADE"
    assert payload["validated"] is True
    assert isinstance(payload["messages"], list) and payload["messages"]
    assert "response" in payload and "content" in payload["response"]


def test_ai_strategy_validate_move_decision(ai_strategy, game_state):
    """Test validation of MOVE decision."""
    # Valid move
    assert ai_strategy._validate_decision(
        TradeAction.MOVE, {"target_sector": 2}, game_state
    )

    # Invalid move - target not in warps
    assert not ai_strategy._validate_decision(
        TradeAction.MOVE, {"target_sector": 99}, game_state
    )

    # Invalid move - no target
    assert not ai_strategy._validate_decision(TradeAction.MOVE, {}, game_state)


def test_ai_strategy_validate_trade_decision(ai_strategy, game_state):
    """Test validation of TRADE decision."""
    # Valid - at port
    assert ai_strategy._validate_decision(TradeAction.TRADE, {}, game_state)

    # Invalid - no port
    game_state_no_port = GameState(
        context="sector_command",
        sector=1,
        has_port=False,
    )
    assert not ai_strategy._validate_decision(
        TradeAction.TRADE, {}, game_state_no_port
    )


def test_ai_strategy_validate_upgrade_decision(ai_strategy, game_state):
    """Test validation of UPGRADE decision."""
    # Valid upgrade types
    assert ai_strategy._validate_decision(
        TradeAction.UPGRADE, {"upgrade_type": "holds"}, game_state
    )
    assert ai_strategy._validate_decision(
        TradeAction.UPGRADE, {"upgrade_type": "fighters"}, game_state
    )
    assert ai_strategy._validate_decision(
        TradeAction.UPGRADE, {"upgrade_type": "shields"}, game_state
    )

    # Invalid upgrade type
    assert not ai_strategy._validate_decision(
        TradeAction.UPGRADE, {"upgrade_type": "invalid"}, game_state
    )


def test_ai_strategy_find_opportunities(ai_strategy, game_state):
    """Test finding opportunities delegates to fallback."""
    opportunities = ai_strategy.find_opportunities(game_state)
    # Should delegate to fallback strategy
    assert isinstance(opportunities, list)
