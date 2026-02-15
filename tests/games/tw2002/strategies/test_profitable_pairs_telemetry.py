# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from time import time

from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorInfo, SectorKnowledge
from bbsbot.games.tw2002.strategies.base import TradeAction, TradeResult
from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair, ProfitablePairsStrategy


def test_profitable_pairs_tracks_invalidation_reason_metrics() -> None:
    strategy = ProfitablePairsStrategy(BotConfig(), SectorKnowledge(knowledge_dir=None, character_name="test"))
    pair = PortPair(
        buy_sector=7,
        sell_sector=8,
        commodity="fuel_ore",
        distance=1,
        path=[7, 8],
        estimated_profit=50,
    )
    strategy._pairs = [pair]

    strategy._invalidate_pair(pair, "buy_path_unreachable")
    strategy._invalidate_pair(pair, "buy_path_unreachable")
    strategy._invalidate_pair(pair, "sell_side_not_buying")

    stats = strategy.stats
    assert stats["pair_invalidations_total"] == 3
    assert stats["pair_invalidations_by_reason"]["buy_path_unreachable"] == 2
    assert stats["pair_invalidations_by_reason"]["sell_side_not_buying"] == 1


def test_profitable_pairs_trade_failure_applies_pair_backoff() -> None:
    strategy = ProfitablePairsStrategy(BotConfig(), SectorKnowledge(knowledge_dir=None, character_name="test"))
    pair = PortPair(
        buy_sector=7,
        sell_sector=8,
        commodity="fuel_ore",
        distance=1,
        path=[7, 8],
        estimated_profit=50,
    )
    strategy._pairs = [pair]
    strategy._current_pair = pair
    strategy._pair_phase = "going_to_buy"

    result = TradeResult(
        success=False,
        action=TradeAction.TRADE,
        turns_used=1,
        trade_attempted=True,
        trade_failure_reason="no_interaction",
        pair_signature="7->8:fuel_ore",
    )
    strategy.record_result(result)

    assert strategy._current_pair is None
    assert strategy._pair_phase == "idle"
    assert strategy._pairs_dirty is True
    assert pair not in strategy._pairs
    assert strategy._pair_failure_streak_by_signature["7->8:fuel_ore"] == 1
    assert strategy._pair_cooldown_until_by_signature["7->8:fuel_ore"] > time()


def test_profitable_pairs_selection_skips_pairs_on_cooldown() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="test")
    knowledge._sectors[2] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[3] = SectorInfo(has_port=True, port_class="BBB")

    def _find_path(start: int, end: int, max_hops: int | None = None):
        if start == 1 and end == 2:
            return [1, 2]
        if start == 2 and end == 3:
            return [2, 3]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    strategy = ProfitablePairsStrategy(BotConfig(), knowledge)
    pair = PortPair(
        buy_sector=2,
        sell_sector=3,
        commodity="fuel_ore",
        distance=1,
        path=[2, 3],
        estimated_profit=0,
    )
    strategy._pairs = [pair]

    state = GameState(context="sector_command", sector=1, credits=600, holds_free=12, warps=[2])
    sig = strategy._pair_signature(pair)
    strategy._pair_cooldown_until_by_signature[sig] = time() + 120
    assert strategy._select_best_pair(state) is None

    strategy._pair_cooldown_until_by_signature[sig] = time() - 1
    assert strategy._select_best_pair(state) == pair


def test_profitable_pairs_prefers_live_port_class_over_stale_status() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="test")
    info = SectorInfo(has_port=True, port_class="SSS")
    info.port_status = {"fuel_ore": "selling", "organics": "buying", "equipment": "buying"}
    knowledge._sectors[77] = info
    strategy = ProfitablePairsStrategy(BotConfig(), knowledge)

    state = GameState(
        context="sector_command",
        sector=77,
        has_port=True,
        port_class="BSS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=4,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[10, 11],
    )
    cargo = {"fuel_ore": 4, "organics": 0, "equipment": 0}

    assert strategy._local_port_side(state, "fuel_ore") == "buying"
    assert strategy._choose_sell_commodity_here(state, cargo) == "fuel_ore"


def test_profitable_pairs_trade_lane_backoff_blocks_pair_selection() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="test")
    knowledge._sectors[2] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[3] = SectorInfo(has_port=True, port_class="BBB")

    def _find_path(start: int, end: int, max_hops: int | None = None):
        if start == 1 and end == 2:
            return [1, 2]
        if start == 2 and end == 3:
            return [2, 3]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    strategy = ProfitablePairsStrategy(BotConfig(), knowledge)
    pair = PortPair(
        buy_sector=2,
        sell_sector=3,
        commodity="fuel_ore",
        distance=1,
        path=[2, 3],
        estimated_profit=0,
    )
    strategy._pairs = [pair]
    state = GameState(context="sector_command", sector=1, credits=600, holds_free=12, warps=[2])

    assert strategy._select_best_pair(state) == pair
    strategy._trade_lane_cooldown_until_by_key[strategy._trade_lane_key(2, "fuel_ore", "buy")] = time() + 120
    assert strategy._select_best_pair(state) is None


def test_profitable_pairs_sector_backoff_blocks_pair_selection() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="test")
    knowledge._sectors[2] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[3] = SectorInfo(has_port=True, port_class="BBB")

    def _find_path(start: int, end: int, max_hops: int | None = None):
        if start == 1 and end == 2:
            return [1, 2]
        if start == 2 and end == 3:
            return [2, 3]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    strategy = ProfitablePairsStrategy(BotConfig(), knowledge)
    pair = PortPair(
        buy_sector=2,
        sell_sector=3,
        commodity="fuel_ore",
        distance=1,
        path=[2, 3],
        estimated_profit=0,
    )
    strategy._pairs = [pair]
    state = GameState(context="sector_command", sector=1, credits=600, holds_free=12, warps=[2])

    assert strategy._select_best_pair(state) == pair
    strategy._trade_sector_cooldown_until_by_sector[2] = time() + 120
    assert strategy._select_best_pair(state) is None


def test_profitable_pairs_trade_failure_updates_trade_lane_cooldown() -> None:
    strategy = ProfitablePairsStrategy(BotConfig(), SectorKnowledge(knowledge_dir=None, character_name="test"))
    result = TradeResult(
        success=False,
        action=TradeAction.TRADE,
        turns_used=1,
        trade_attempted=True,
        trade_failure_reason="wrong_side",
        pair_signature="7->8:fuel_ore",
        trade_sector=7,
        trade_commodity="fuel_ore",
        trade_side="buy",
    )
    strategy.record_result(result)
    lane = strategy._trade_lane_key(7, "fuel_ore", "buy")
    assert strategy._trade_lane_failure_streak_by_key[lane] == 1
    assert strategy._trade_lane_cooldown_until_by_key[lane] > time()
    opposite_lane = strategy._trade_lane_key(7, "fuel_ore", "sell")
    assert strategy._trade_lane_cooldown_until_by_key[opposite_lane] > time()


def test_profitable_pairs_marks_throughput_degraded_on_low_success_rate() -> None:
    strategy = ProfitablePairsStrategy(BotConfig(), SectorKnowledge(knowledge_dir=None, character_name="test"))
    for _ in range(30):
        strategy._record_trade_attempt_sample(False)
    assert strategy._is_trade_throughput_degraded() is True


def test_profitable_pairs_detects_structural_failure_storm() -> None:
    strategy = ProfitablePairsStrategy(BotConfig(), SectorKnowledge(knowledge_dir=None, character_name="test"))
    for _ in range(16):
        strategy._record_trade_failure_reason("wrong_side")
    for _ in range(4):
        strategy._record_trade_failure_reason("timeout")
    assert strategy._is_structural_failure_storm() is True


def test_profitable_pairs_anti_collapse_disable_skips_lane_backoff() -> None:
    cfg = BotConfig()
    cfg.trading.profitable_pairs.anti_collapse_override.enabled = False
    strategy = ProfitablePairsStrategy(cfg, SectorKnowledge(knowledge_dir=None, character_name="test"))
    strategy._apply_trade_lane_backoff(7, "fuel_ore", "buy", "wrong_side")
    assert strategy._trade_lane_cooldown_until_by_key == {}
    assert strategy._trade_sector_cooldown_until_by_sector == {}


def test_profitable_pairs_anti_collapse_override_thresholds_apply() -> None:
    cfg = BotConfig()
    cfg.trading.profitable_pairs.anti_collapse_override.throughput_degraded_min_samples = 5
    cfg.trading.profitable_pairs.anti_collapse_override.throughput_degraded_success_rate_lt = 0.5
    strategy = ProfitablePairsStrategy(cfg, SectorKnowledge(knowledge_dir=None, character_name="test"))
    for _ in range(4):
        strategy._record_trade_attempt_sample(False)
    assert strategy._is_trade_throughput_degraded() is False
    strategy._record_trade_attempt_sample(False)
    assert strategy._is_trade_throughput_degraded() is True
