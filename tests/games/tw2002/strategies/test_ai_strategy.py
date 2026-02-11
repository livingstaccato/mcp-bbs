"""Tests for AI strategy."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    strategy = AIStrategy(bot_config, sector_knowledge)
    # Skip Ollama verification in tests
    strategy._ollama_verified = True
    return strategy


def test_ai_strategy_init(ai_strategy):
    """Test AI strategy initialization."""
    assert ai_strategy.name == "ai_strategy"
    assert ai_strategy.consecutive_failures == 0
    assert ai_strategy.llm_manager is not None
    assert ai_strategy.prompt_builder is not None
    assert ai_strategy.parser is not None
    assert ai_strategy.fallback is not None
    assert ai_strategy.active_managed_strategy == "profitable_pairs"


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

        assert action is not None
        assert ai_strategy.consecutive_failures == 0


@pytest.mark.asyncio
async def test_ai_strategy_fallback_on_failure(ai_strategy, game_state):
    """Test graduated fallback activation on failures."""
    # Simulate LLM failures
    with patch.object(ai_strategy.llm_manager, "chat", side_effect=Exception("LLM error")):
        # First failure - retry immediately (no fallback cooldown)
        action1, _ = await ai_strategy._get_next_action_async(game_state)
        assert ai_strategy.consecutive_failures == 1
        assert ai_strategy.fallback_until_turn == 0  # No cooldown on single failure

        # Second failure - enters short fallback (2 turns)
        action2, _ = await ai_strategy._get_next_action_async(game_state)
        assert ai_strategy.consecutive_failures == 2
        assert ai_strategy.fallback_until_turn > 0  # Now in fallback

        # Third attempt - still in fallback cooldown, uses fallback directly
        action3, _ = await ai_strategy._get_next_action_async(game_state)
        # Failures stay at 2 because LLM wasn't called (in fallback mode)
        assert ai_strategy.consecutive_failures == 2
        assert action3 is not None

        # Fourth attempt - fallback expired, LLM tried again and fails
        action4, _ = await ai_strategy._get_next_action_async(game_state)
        # Now it tried LLM again (cooldown expired) and failed
        assert ai_strategy.consecutive_failures == 3
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
        assert action is not None

    # Ensure decision log was written.
    calls = [c for c in mock_session_logger.log_event.call_args_list if c.args and c.args[0] == "llm.decision"]
    assert calls, "Expected at least one llm.decision event"
    payload = calls[-1].args[1]
    assert payload["parsed"]["action"] in {a.name for a in TradeAction}
    assert payload["validated"] is True
    assert isinstance(payload["messages"], list) and payload["messages"]
    assert "response" in payload and "content" in payload["response"]


@pytest.mark.asyncio
async def test_ai_strategy_llm_can_delegate_managed_strategy(ai_strategy, game_state):
    """AI can choose a concrete strategy and delegate execution to it."""
    mock_response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content='{"strategy": "profitable_pairs", "action": "TRADE", "parameters": {}}',
        ),
        model="llama2",
    )
    managed = MagicMock()
    managed.get_next_action.return_value = (TradeAction.EXPLORE, {"direction": 2})
    managed.set_policy.return_value = None

    with (
        patch.object(ai_strategy.llm_manager, "chat", return_value=mock_response),
        patch.object(ai_strategy, "_get_managed_strategy", return_value=managed),
    ):
        action, params = await ai_strategy._get_next_action_async(game_state)

    assert action == TradeAction.EXPLORE
    assert params["direction"] == 2
    assert ai_strategy.active_managed_strategy == "profitable_pairs"


@pytest.mark.asyncio
async def test_ai_strategy_supervisor_autopilot_uses_llm_periodically(ai_strategy, game_state):
    """LLM decides a plan, then supervisor runs managed strategy without re-calling LLM each turn."""
    mock_response = ChatResponse(
        message=ChatMessage(
            role="assistant",
            content='{"strategy":"profitable_pairs","review_after_turns":12,"action":"MOVE","parameters":{"target_sector":2}}',
        ),
        model="llama2",
    )
    managed = MagicMock()
    managed.get_next_action.return_value = (TradeAction.MOVE, {"target_sector": 2, "path": [1, 2]})
    managed.set_policy.return_value = None

    with (
        patch.object(ai_strategy.llm_manager, "chat", new_callable=AsyncMock, return_value=mock_response) as llm_chat,
        patch.object(ai_strategy, "_get_managed_strategy", return_value=managed),
    ):
        # Turn 1: LLM should run and schedule next review.
        action1, _ = await ai_strategy._get_next_action_async(game_state)
        assert action1 == TradeAction.MOVE
        assert llm_chat.await_count == 1
        assert ai_strategy._next_llm_turn >= ai_strategy._current_turn + 1

        # Turn 2: supervisor autopilot should execute managed strategy without another LLM call.
        action2, _ = await ai_strategy._get_next_action_async(game_state)
        assert action2 == TradeAction.MOVE
        assert llm_chat.await_count == 1


def test_ai_strategy_done_requires_no_turns(ai_strategy, game_state):
    """DONE is invalid while turns remain."""
    assert not ai_strategy._validate_decision(TradeAction.DONE, {}, game_state)
    game_state.turns_left = 0
    assert ai_strategy._validate_decision(TradeAction.DONE, {}, game_state)


def test_ai_strategy_ai_direct_resolves_to_managed(ai_strategy):
    params = {"strategy": "ai_direct"}
    resolved = ai_strategy.resolve_requested_strategy(params)
    assert resolved == "profitable_pairs"


def test_ai_strategy_validate_move_decision(ai_strategy, game_state):
    """Test validation of MOVE decision."""
    # Valid move
    assert ai_strategy._validate_decision(TradeAction.MOVE, {"target_sector": 2}, game_state)

    # Invalid move - target not in warps
    assert not ai_strategy._validate_decision(TradeAction.MOVE, {"target_sector": 99}, game_state)

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
    assert not ai_strategy._validate_decision(TradeAction.TRADE, {}, game_state_no_port)
    assert not ai_strategy._validate_decision(
        TradeAction.TRADE,
        {"commodity": "fuel_ore|organics"},
        game_state,
    )


def test_ai_strategy_validate_upgrade_decision(ai_strategy, game_state):
    """Test validation of UPGRADE decision."""
    # Valid upgrade types
    assert ai_strategy._validate_decision(TradeAction.UPGRADE, {"upgrade_type": "holds"}, game_state)
    assert ai_strategy._validate_decision(TradeAction.UPGRADE, {"upgrade_type": "fighters"}, game_state)
    assert ai_strategy._validate_decision(TradeAction.UPGRADE, {"upgrade_type": "shields"}, game_state)

    # Invalid upgrade type
    assert not ai_strategy._validate_decision(TradeAction.UPGRADE, {"upgrade_type": "invalid"}, game_state)


def test_ai_strategy_validate_review_after_turns(ai_strategy, game_state):
    assert ai_strategy._validate_decision(TradeAction.MOVE, {"target_sector": 2, "review_after_turns": 8}, game_state)
    assert not ai_strategy._validate_decision(TradeAction.MOVE, {"target_sector": 2, "review_after_turns": 0}, game_state)
    assert not ai_strategy._validate_decision(
        TradeAction.MOVE,
        {"target_sector": 2, "review_after_turns": 999},
        game_state,
    )


def test_ai_strategy_urgent_triggers_respect_spacing(ai_strategy, game_state):
    ai_strategy._current_turn = 20
    ai_strategy._next_llm_turn = 30
    ai_strategy._last_llm_turn = 19
    ai_strategy._turns_used = 20
    ai_strategy._trades_executed = 0
    should_wake, reason = ai_strategy.should_wake_llm(game_state, stuck_action=None)
    assert not should_wake
    assert reason.startswith("autopilot_until_")

    ai_strategy._last_llm_turn = 15
    should_wake2, reason2 = ai_strategy.should_wake_llm(game_state, stuck_action=None)
    assert should_wake2
    assert reason2 == "no_trade_trigger"


def test_ai_strategy_find_opportunities(ai_strategy, game_state):
    """Test finding opportunities delegates to fallback."""
    opportunities = ai_strategy.find_opportunities(game_state)
    # Should delegate to fallback strategy
    assert isinstance(opportunities, list)


def test_ai_strategy_goal_contract_failure_eval_and_enforce(ai_strategy, game_state):
    ai_strategy._settings.goal_contract_enabled = True
    ai_strategy._settings.goal_contract_window_turns = 5
    ai_strategy._settings.goal_contract_min_trades = 1
    ai_strategy._settings.goal_contract_min_profit_delta = 10
    ai_strategy._settings.goal_contract_min_credits_delta = 10
    ai_strategy._settings.goal_contract_fail_strategy = "opportunistic"
    ai_strategy._settings.goal_contract_fail_policy = "conservative"
    ai_strategy._settings.goal_contract_fail_review_turns = 3

    ai_strategy._current_turn = 20
    ai_strategy._turns_used = 20
    ai_strategy._trades_executed = 0
    ai_strategy._total_profit = 0
    ai_strategy._active_managed_strategy = "profitable_pairs"
    ai_strategy._goal_contract_baseline = {
        "turn": 10,
        "turns_used": 10,
        "trades_executed": 0,
        "total_profit": 0,
        "credits": 1000,
        "goal_id": "profit",
        "strategy": "profitable_pairs",
        "reason": "test",
    }
    game_state.credits = 1000

    evaluation = ai_strategy.evaluate_goal_contract(game_state)
    assert evaluation is not None
    assert evaluation["failed"] is True
    assert "trades<1" in evaluation["reasons"]

    forced_strategy, forced_policy, review_turns = ai_strategy.enforce_goal_contract_failure(evaluation)
    assert forced_strategy == "opportunistic"
    assert forced_policy == "conservative"
    assert review_turns == 3
    assert ai_strategy.active_managed_strategy == "opportunistic"
    assert ai_strategy.policy == "conservative"


@pytest.mark.asyncio
async def test_ai_strategy_orchestration_contract_forces_without_llm(ai_strategy, game_state):
    ai_strategy._settings.goal_contract_enabled = True
    ai_strategy._settings.goal_contract_window_turns = 5
    ai_strategy._settings.goal_contract_min_trades = 1
    ai_strategy._settings.goal_contract_min_profit_delta = 10
    ai_strategy._settings.goal_contract_min_credits_delta = 10
    ai_strategy._settings.goal_contract_fail_strategy = "opportunistic"
    ai_strategy._settings.goal_contract_fail_policy = "conservative"
    ai_strategy._settings.goal_contract_fail_review_turns = 4

    ai_strategy._current_turn = 20
    ai_strategy._turns_used = 20
    ai_strategy._trades_executed = 0
    ai_strategy._total_profit = 0
    ai_strategy._goal_contract_baseline = {
        "turn": 10,
        "turns_used": 10,
        "trades_executed": 0,
        "total_profit": 0,
        "credits": 1000,
        "goal_id": "profit",
        "strategy": "profitable_pairs",
        "reason": "test",
    }
    game_state.credits = 1000

    managed = MagicMock()
    managed.get_next_action.return_value = (TradeAction.MOVE, {"target_sector": 2, "path": [1, 2]})
    managed.set_policy.return_value = None

    with (
        patch.object(ai_strategy.llm_manager, "chat", new_callable=AsyncMock) as llm_chat,
        patch.object(ai_strategy, "_get_managed_strategy", return_value=managed),
    ):
        action, params = await ai_strategy._get_next_action_async(game_state)

    assert action == TradeAction.MOVE
    assert params["target_sector"] == 2
    assert params["__meta"]["decision_source"] == "goal_contract"
    assert params["__meta"]["forced_contract"] is True
    assert llm_chat.await_count == 0
