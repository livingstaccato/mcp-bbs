# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

import time

from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorInfo, SectorKnowledge
from bbsbot.games.tw2002.strategies.base import TradeAction, TradeResult
from bbsbot.games.tw2002.strategies.profitable_pairs import ProfitablePairsStrategy


def test_price_profit_estimate_is_capped_by_liquidity() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # Buy port sells commodity at 10/unit, but only 3 units available.
    buy_info = SectorInfo(has_port=True, port_class="SBB")
    buy_info.port_prices = {"fuel_ore": {"sell": 10}}
    buy_info.port_trading_units = {"fuel_ore": 3}
    knowledge._sectors[2] = buy_info

    # Sell port buys commodity at 20/unit, but only 2 units demand.
    sell_info = SectorInfo(has_port=True, port_class="BSS")
    sell_info.port_prices = {"fuel_ore": {"buy": 20}}
    sell_info.port_trading_units = {"fuel_ore": 2}
    knowledge._sectors[3] = sell_info

    state = GameState(context="sector_command", sector=1, credits=10_000, holds_free=10)

    # Build a minimal pair object compatible with the internal estimator.
    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    pair = PortPair(buy_sector=2, sell_sector=3, commodity="fuel_ore", distance=1, path=[2, 3], estimated_profit=0)

    # profit_per_unit=10; qty cap=min(holds=10, affordable=1000, supply=3, demand=2) => 2
    assert strat._estimate_profit_for_pair(state, pair) == 20


def test_low_credit_min_profit_gate_is_relaxed() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    low_credit_state = GameState(context="sector_command", sector=1, credits=300, holds_free=20)
    _, min_ppt = strat._effective_limits(low_credit_state)
    assert min_ppt <= 5


def test_recommended_buy_qty_uses_holds_total_when_holds_free_missing() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    buy_info = SectorInfo(has_port=True, port_class="SSS")
    buy_info.port_prices = {"fuel_ore": {"sell": 50}}
    buy_info.port_trading_units = {"fuel_ore": 500}
    sell_info = SectorInfo(has_port=True, port_class="BSS")
    sell_info.port_prices = {"fuel_ore": {"buy": 80}}
    sell_info.port_trading_units = {"fuel_ore": 500}
    knowledge._sectors[2] = buy_info
    knowledge._sectors[3] = sell_info

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    pair = PortPair(buy_sector=2, sell_sector=3, commodity="fuel_ore", distance=1, path=[2, 3], estimated_profit=0)
    state = GameState(
        context="sector_command",
        sector=2,
        credits=600,
        holds_total=20,
        holds_free=None,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )
    qty = strat._recommended_buy_qty(state, pair)
    assert qty >= 3


def test_select_best_pair_scans_beyond_first_twenty_candidates() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    # Create 25 synthetic candidates. Only the last one is reachable.
    strat._pairs = [
        PortPair(buy_sector=100 + i, sell_sector=200 + i, commodity="fuel_ore", distance=1, path=[100 + i, 200 + i])
        for i in range(25)
    ]

    orig_find_path = knowledge.find_path
    try:

        def _find_path(src: int, dst: int, max_hops: int | None = None):
            if dst == 124:
                return [src, dst]
            return None

        knowledge.find_path = _find_path  # type: ignore[assignment]
        state = GameState(context="sector_command", sector=1, credits=500, holds_free=10)
        best = strat._select_best_pair(state)
        assert best is not None
        assert best.buy_sector == 124
    finally:
        knowledge.find_path = orig_find_path  # type: ignore[assignment]


def test_known_unprofitable_pair_is_skipped() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    buy_info = SectorInfo(has_port=True, port_class="SBB")
    buy_info.port_prices = {"fuel_ore": {"sell": 50}}
    sell_info = SectorInfo(has_port=True, port_class="BSS")
    sell_info.port_prices = {"fuel_ore": {"buy": 40}}
    knowledge._sectors[2] = buy_info
    knowledge._sectors[3] = sell_info

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    pair = PortPair(buy_sector=2, sell_sector=3, commodity="fuel_ore", distance=1, path=[2, 3], estimated_profit=0)
    strat._pairs = [pair]

    orig_find_path = knowledge.find_path
    try:
        knowledge.find_path = lambda src, dst, max_hops=None: [src, dst]  # type: ignore[assignment]
        state = GameState(context="sector_command", sector=1, credits=1000, holds_free=10)
        assert strat._recommended_buy_qty(state, pair) == 0
        assert strat._select_best_pair(state) is None
    finally:
        knowledge.find_path = orig_find_path  # type: ignore[assignment]


def test_select_best_pair_skips_far_reposition_for_low_credit_bots() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    near_pair = PortPair(buy_sector=2, sell_sector=3, commodity="fuel_ore", distance=1, path=[2, 3])
    far_pair = PortPair(buy_sector=99, sell_sector=100, commodity="fuel_ore", distance=1, path=[99, 100])
    strat._pairs = [near_pair, far_pair]

    near_buy = SectorInfo(has_port=True, port_class="SSS")
    near_buy.port_prices = {"fuel_ore": {"sell": 10}}
    near_sell = SectorInfo(has_port=True, port_class="BSS")
    near_sell.port_prices = {"fuel_ore": {"buy": 14}}
    far_buy = SectorInfo(has_port=True, port_class="SSS")
    far_buy.port_prices = {"fuel_ore": {"sell": 10}}
    far_sell = SectorInfo(has_port=True, port_class="BSS")
    far_sell.port_prices = {"fuel_ore": {"buy": 20}}
    knowledge._sectors[2] = near_buy
    knowledge._sectors[3] = near_sell
    knowledge._sectors[99] = far_buy
    knowledge._sectors[100] = far_sell

    orig_find_path = knowledge.find_path
    try:
        def _find_path(src: int, dst: int, max_hops: int | None = None):
            if dst == 2:
                return [1, 2]
            if dst == 99:
                return [1, 11, 22, 33, 44, 55, 66, 77, 88, 99]
            if src == 2 and dst == 3:
                return [2, 3]
            if src == 99 and dst == 100:
                return [99, 100]
            return None

        knowledge.find_path = _find_path  # type: ignore[assignment]
        low_credit_state = GameState(context="sector_command", sector=1, credits=300, holds_free=20)
        best = strat._select_best_pair(low_credit_state)
        assert best is not None
        assert best.buy_sector == 2
    finally:
        knowledge.find_path = orig_find_path  # type: ignore[assignment]


def test_select_best_pair_prefers_affordable_unpriced_commodity() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    # Both pairs are structurally valid but have no price quotes.
    # Low-credit bot should avoid equipment-heavy unpriced probes.
    fuel_pair = PortPair(buy_sector=2, sell_sector=3, commodity="fuel_ore", distance=1, path=[2, 3])
    equip_pair = PortPair(buy_sector=4, sell_sector=5, commodity="equipment", distance=1, path=[4, 5])
    strat._pairs = [equip_pair, fuel_pair]

    knowledge._sectors[2] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[3] = SectorInfo(has_port=True, port_class="BSS")
    knowledge._sectors[4] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[5] = SectorInfo(has_port=True, port_class="SSB")

    orig_find_path = knowledge.find_path
    try:

        def _find_path(src: int, dst: int, max_hops: int | None = None):
            if dst in {2, 4}:
                return [1, dst]
            if src == 2 and dst == 3:
                return [2, 3]
            if src == 4 and dst == 5:
                return [4, 5]
            return None

        knowledge.find_path = _find_path  # type: ignore[assignment]
        low_credit_state = GameState(context="sector_command", sector=1, credits=300, holds_total=20, holds_free=None)
        best = strat._select_best_pair(low_credit_state)
        assert best is not None
        assert best.commodity == "fuel_ore"
    finally:
        knowledge.find_path = orig_find_path  # type: ignore[assignment]


def test_local_bootstrap_trade_prefers_selling_held_cargo() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    info = SectorInfo(has_port=True, port_class="BSS")
    info.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    knowledge._sectors[10] = info

    state = GameState(
        context="sector_command",
        sector=10,
        credits=300,
        holds_free=10,
        has_port=True,
        cargo_fuel_ore=2,
        cargo_organics=0,
        cargo_equipment=0,
    )

    action, params = strat._local_bootstrap_trade(state)  # type: ignore[misc]
    assert action == TradeAction.TRADE
    assert params.get("action") == "sell"
    assert params["opportunity"].commodity == "fuel_ore"


def test_pair_buy_leg_replans_when_local_port_no_longer_selling_target() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    pair = PortPair(buy_sector=10, sell_sector=20, commodity="fuel_ore", distance=1, path=[10, 20])
    strat._pairs = [pair]
    strat._current_pair = pair
    strat._pair_phase = "going_to_buy"

    # BSS means fuel_ore is buying (not selling) -> invalid for buy leg.
    knowledge._sectors[10] = SectorInfo(has_port=True, port_class="BSS")
    state = GameState(
        context="sector_command",
        sector=10,
        has_port=True,
        port_class="BSS",
        credits=300,
        holds_free=20,
        warps=[11],
    )

    action, params = strat.get_next_action(state)
    assert action in {TradeAction.EXPLORE, TradeAction.MOVE, TradeAction.WAIT}
    assert strat._pair_phase == "idle"
    assert strat._current_pair is None


def test_pair_sell_leg_reroutes_liquidation_when_local_port_not_buying() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    pair = PortPair(buy_sector=10, sell_sector=20, commodity="fuel_ore", distance=1, path=[10, 20])
    strat._pairs = [pair]
    strat._current_pair = pair
    strat._pair_phase = "going_to_sell"

    # Sell leg target now invalid: SSS means port sells all commodities.
    knowledge._sectors[20] = SectorInfo(has_port=True, port_class="SSS")
    # Nearby known buyer for fuel_ore.
    knowledge._sectors[21] = SectorInfo(has_port=True, port_class="BSS")
    knowledge.find_path = lambda start, end, max_hops=100: [20, 21] if end == 21 else None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=20,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=15,
        cargo_fuel_ore=5,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[21],
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.MOVE
    assert int(params.get("target_sector", 0)) == 21
    assert strat._pair_phase == "idle"
    assert strat._current_pair is None


def test_local_bootstrap_trade_does_not_speculatively_buy_without_pair() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    info = SectorInfo(has_port=True, port_class="SBS")
    info.port_status = {"fuel_ore": "selling", "organics": "buying", "equipment": "selling"}
    info.port_prices = {
        "fuel_ore": {"sell": 120},
        "equipment": {"sell": 500},
    }
    knowledge._sectors[11] = info

    state = GameState(
        context="sector_command",
        sector=11,
        credits=300,
        holds_free=10,
        has_port=True,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    assert strat._local_bootstrap_trade(state) is None  # type: ignore[misc]


def test_local_bootstrap_trade_uses_port_class_when_market_rows_missing() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # SSB means fuel/organics are selling, equipment is buying.
    info = SectorInfo(has_port=True, port_class="SSB")
    knowledge._sectors[12] = info

    state = GameState(
        context="sector_command",
        sector=12,
        credits=300,
        holds_free=10,
        has_port=True,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    assert strat._local_bootstrap_trade(state) is None  # type: ignore[misc]


def test_discover_pairs_prefers_live_port_status_over_static_port_class() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # Static class says sector 20 sells fuel_ore, but live status says buying.
    a = SectorInfo(has_port=True, port_class="SBB")
    a.port_status = {"fuel_ore": "buying"}
    knowledge._sectors[20] = a

    # Static class says sector 21 buys fuel_ore, but live status says selling.
    b = SectorInfo(has_port=True, port_class="BSS")
    b.port_status = {"fuel_ore": "selling"}
    knowledge._sectors[21] = b

    knowledge.find_path = lambda start, end, max_hops=100: [start, end]  # type: ignore[assignment]
    strat._discover_pairs(max_hops=3)  # type: ignore[misc]

    fuel_pairs = [p for p in strat._pairs if p.commodity == "fuel_ore"]  # type: ignore[attr-defined]
    assert fuel_pairs
    assert any(p.buy_sector == 21 and p.sell_sector == 20 for p in fuel_pairs)


def test_local_bootstrap_trade_safe_buy_requires_nearby_known_buyer() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # Current port sells fuel ore.
    sell_here = SectorInfo(has_port=True, port_class="SSS")
    sell_here.port_status = {"fuel_ore": "selling", "organics": "selling", "equipment": "selling"}
    sell_here.port_prices = {"fuel_ore": {"sell": 40}}
    sell_here.port_trading_units = {"fuel_ore": 300}
    knowledge._sectors[50] = sell_here

    # Nearby known buyer for fuel ore.
    buyer = SectorInfo(has_port=True, port_class="BSS")
    buyer.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    knowledge._sectors[51] = buyer

    knowledge.find_path = lambda start, end, max_hops=100: [50, 51] if end == 51 else None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=50,
        credits=500,
        holds_free=10,
        has_port=True,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    action, params = strat._local_bootstrap_trade(state)  # type: ignore[misc]
    assert action == TradeAction.TRADE
    assert params.get("action") == "buy"
    assert params["opportunity"].commodity == "fuel_ore"
    assert int(params.get("max_quantity", 0)) >= 1


def test_local_bootstrap_trade_uses_multi_commodity_sweep_when_safe() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    sell_here = SectorInfo(has_port=True, port_class="SSS")
    sell_here.port_status = {"fuel_ore": "selling", "organics": "selling", "equipment": "selling"}
    sell_here.port_prices = {"fuel_ore": {"sell": 20}, "organics": {"sell": 30}}
    sell_here.port_trading_units = {"fuel_ore": 300, "organics": 300}
    knowledge._sectors[50] = sell_here

    buyer_fuel = SectorInfo(has_port=True, port_class="BSS")
    buyer_fuel.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    knowledge._sectors[51] = buyer_fuel

    buyer_org = SectorInfo(has_port=True, port_class="SBS")
    buyer_org.port_status = {"fuel_ore": "selling", "organics": "buying", "equipment": "selling"}
    knowledge._sectors[52] = buyer_org

    knowledge.find_path = lambda start, end, max_hops=100: [50, end] if end in {51, 52} else None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=50,
        credits=700,
        holds_free=12,
        has_port=True,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    action, params = strat._local_bootstrap_trade(state)  # type: ignore[misc]
    assert action == TradeAction.TRADE
    assert params.get("action") == "buy"
    sequence = list(params.get("commodity_sequence") or [])
    assert len(sequence) >= 2
    assert "fuel_ore" in sequence
    assert "organics" in sequence
    qty_map = dict(params.get("max_quantity_by_commodity") or {})
    assert int(qty_map.get("fuel_ore", 0)) >= 1
    assert int(qty_map.get("organics", 0)) >= 1


def test_unknown_holds_free_still_allows_minimum_trade_planning() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    buy_info = SectorInfo(has_port=True, port_class="SBB")
    buy_info.port_prices = {"fuel_ore": {"sell": 20}}
    sell_info = SectorInfo(has_port=True, port_class="BSS")
    sell_info.port_prices = {"fuel_ore": {"buy": 30}}
    knowledge._sectors[2] = buy_info
    knowledge._sectors[3] = sell_info

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    pair = PortPair(buy_sector=2, sell_sector=3, commodity="fuel_ore", distance=1, path=[2, 3], estimated_profit=0)

    state = GameState(context="sector_command", sector=2, credits=300, holds_free=None)
    assert strat._recommended_buy_qty(state, pair) >= 1
    assert strat._estimate_profit_for_pair(state, pair) > 0


def test_cargo_liquidation_uses_multi_commodity_sweep_when_local_buyers_exist() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    info = SectorInfo(has_port=True, port_class="BBS")
    info.port_status = {"fuel_ore": "buying", "organics": "buying", "equipment": "selling"}
    knowledge._sectors[88] = info

    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="BBS",
        credits=900,
        holds_free=20,
        cargo_fuel_ore=4,
        cargo_organics=3,
        cargo_equipment=0,
        warps=[89, 90],
    )
    cargo = {"fuel_ore": 4, "organics": 3, "equipment": 0}

    action, params = strat._cargo_liquidation_action(state, cargo)  # type: ignore[misc]
    assert action == TradeAction.TRADE
    assert params.get("action") == "sell"
    sequence = list(params.get("commodity_sequence") or [])
    assert sequence[:2] == ["fuel_ore", "organics"]
    qty_map = dict(params.get("max_quantity_by_commodity") or {})
    assert int(qty_map.get("fuel_ore", 0)) == 4
    assert int(qty_map.get("organics", 0)) == 3


def test_choose_sell_commodity_skips_blocked_lane() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    info = SectorInfo(has_port=True, port_class="BBS")
    info.port_status = {"fuel_ore": "buying", "organics": "buying", "equipment": "selling"}
    knowledge._sectors[88] = info

    lane_key = strat._trade_lane_key(88, "fuel_ore", "sell")
    strat._trade_lane_cooldown_until_by_key[lane_key] = time.time() + 120

    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="BBS",
        credits=900,
        holds_free=20,
        cargo_fuel_ore=4,
        cargo_organics=3,
        cargo_equipment=0,
    )
    cargo = {"fuel_ore": 4, "organics": 3, "equipment": 0}

    chosen = strat._choose_sell_commodity_here(state, cargo)  # type: ignore[misc]
    assert chosen == "organics"


def test_find_best_sell_target_skips_blocked_lane() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    blocked = SectorInfo(has_port=True, port_class="BSS")
    blocked.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    alt = SectorInfo(has_port=True, port_class="BSS")
    alt.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    knowledge._sectors[200] = blocked
    knowledge._sectors[201] = alt

    def _find_path(src: int, dst: int, max_hops: int | None = None):
        if dst == 200:
            return [100, 150, 200]
        if dst == 201:
            return [100, 201]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    lane_key = strat._trade_lane_key(200, "fuel_ore", "sell")
    strat._trade_lane_cooldown_until_by_key[lane_key] = time.time() + 120

    state = GameState(context="sector_command", sector=100, credits=500, holds_free=10)
    cargo = {"fuel_ore": 3, "organics": 0, "equipment": 0}
    best = strat._find_best_sell_target(state, cargo, max_hops=20)  # type: ignore[misc]
    assert best is not None
    assert int(best["sector"]) == 201


def test_multi_commodity_sweep_allowed_with_low_but_nonzero_success_rate() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # Isolate the success-rate gate for this test.
    strat._is_trade_throughput_degraded = lambda: False  # type: ignore[assignment]
    strat._is_structural_failure_storm = lambda: False  # type: ignore[assignment]
    strat._is_wrong_side_storm_active = lambda turns_used: False  # type: ignore[assignment]

    # 10% recent success should still allow sweep mode.
    strat._recent_trade_attempt_successes.clear()
    strat._recent_trade_attempt_successes.extend([False] * 18 + [True] * 2)
    assert strat._allow_multi_commodity_sweep() is True


def test_multi_commodity_sweep_blocked_in_severe_collapse() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # 0% recent success should still disable sweep mode.
    strat._recent_trade_attempt_successes.clear()
    strat._recent_trade_attempt_successes.extend([False] * 20)
    assert strat._allow_multi_commodity_sweep() is False


def test_select_best_pair_prefers_viable_priced_pair_over_unpriced() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # Priced pair: small but positive profit.
    buy_info = SectorInfo(has_port=True, port_class="SBB")
    buy_info.port_prices = {"fuel_ore": {"sell": 100}}
    sell_info = SectorInfo(has_port=True, port_class="BSS")
    sell_info.port_prices = {"fuel_ore": {"buy": 101}}
    knowledge._sectors[10] = buy_info
    knowledge._sectors[11] = sell_info

    # Unpriced pair: structurally valid but no market data.
    knowledge._sectors[20] = SectorInfo(has_port=True, port_class="SBB")
    knowledge._sectors[21] = SectorInfo(has_port=True, port_class="BSS")

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    priced = PortPair(
        buy_sector=10, sell_sector=11, commodity="fuel_ore", distance=1, path=[10, 11], estimated_profit=0
    )
    unpriced = PortPair(
        buy_sector=20, sell_sector=21, commodity="fuel_ore", distance=1, path=[20, 21], estimated_profit=0
    )
    strat._pairs = [unpriced, priced]

    orig_find_path = knowledge.find_path
    try:
        # Make both reachable from current sector.
        knowledge.find_path = lambda src, dst, max_hops=None: [src, dst]  # type: ignore[assignment]
        state = GameState(context="sector_command", sector=1, credits=300, holds_free=1)
        best = strat._select_best_pair(state)
        assert best is not None
        assert best.buy_sector == 10
        assert best.sell_sector == 11
    finally:
        knowledge.find_path = orig_find_path  # type: ignore[assignment]


def test_explore_streak_resets_on_profitable_trade() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    strat.record_result(TradeResult(success=True, action=TradeAction.EXPLORE, profit=0, turns_used=1))
    strat.record_result(TradeResult(success=True, action=TradeAction.MOVE, profit=0, turns_used=1))
    assert strat._explore_since_profit >= 2

    strat.record_result(TradeResult(success=True, action=TradeAction.TRADE, profit=50, turns_used=1))
    assert strat._explore_since_profit == 0


def test_explore_for_ports_falls_back_to_known_warps_when_live_warps_missing() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    knowledge.update_sector(42, {"warps": [43, 44]})
    state = GameState(context="sector_command", sector=42, warps=[])

    action, params = strat._explore_for_ports(state)  # type: ignore[misc]
    assert action in (TradeAction.EXPLORE, TradeAction.MOVE)
    assert (params.get("direction") or params.get("target_sector")) in {43, 44}


def test_explore_for_ports_waits_with_reason_when_no_warps_known() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    state = GameState(context="sector_command", sector=77, warps=[])
    action, params = strat._explore_for_ports(state)  # type: ignore[misc]

    assert action == TradeAction.WAIT
    assert params.get("reason") == "no_warps"


def test_low_cash_recovery_sells_local_cargo_before_buying() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    info = SectorInfo(has_port=True, port_class="BSS")
    info.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    knowledge._sectors[55] = info

    state = GameState(
        context="sector_command",
        sector=55,
        has_port=True,
        port_class="BSS",
        credits=120,
        holds_free=10,
        cargo_fuel_ore=4,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[60, 61],
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.TRADE
    assert params.get("action") == "sell"
    assert params.get("urgency") == "low_cash_recovery"
    assert params["opportunity"].commodity == "fuel_ore"


def test_low_cash_recovery_moves_to_known_buyer_when_not_at_port() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    knowledge._sectors[200] = SectorInfo(has_port=True, port_class="BBS")
    knowledge.find_path = lambda start, end, max_hops=100: [100, end] if end == 200 else None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=100,
        has_port=False,
        credits=150,
        holds_free=10,
        cargo_fuel_ore=3,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[101, 102],
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.MOVE
    assert params.get("target_sector") == 200
    assert params.get("urgency") == "low_cash_recovery"


def test_low_cash_without_cargo_uses_bootstrap_instead_of_forced_explore() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    expected = (
        TradeAction.TRADE,
        {
            "action": "buy",
            "urgency": "bootstrap_trade",
        },
    )
    strat._local_bootstrap_trade = lambda _state: expected  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=40,
        has_port=True,
        port_class="SSB",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[41, 42],
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.TRADE
    assert params.get("action") == "buy"
    assert params.get("urgency") == "bootstrap_trade"


def test_loop_break_avoids_abab_ping_pong_when_unproductive() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # Simulate prolonged non-profitable movement pattern A-B-A-B.
    strat._explore_since_profit = 8
    strat._recent_sectors.extend([10, 20, 10])

    state = GameState(
        context="sector_command",
        sector=20,
        has_port=False,
        credits=400,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[10, 30],
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.EXPLORE
    assert params.get("direction") == 30
    assert params.get("urgency") == "loop_break"


def test_cargo_liquidation_sells_local_when_not_low_cash() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    info = SectorInfo(has_port=True, port_class="BSS")
    info.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    knowledge._sectors[88] = info

    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="BSS",
        credits=800,
        holds_free=10,
        cargo_fuel_ore=5,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[89, 90],
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.TRADE
    assert params.get("action") == "sell"
    assert params.get("urgency") == "cargo_liquidation"
    assert params["opportunity"].commodity == "fuel_ore"


def test_cargo_liquidation_moves_to_buyer_before_new_buys() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    # Sector 200 buys fuel ore; from 100 we can route there.
    knowledge._sectors[200] = SectorInfo(has_port=True, port_class="BBS")
    knowledge.find_path = lambda start, end, max_hops=100: [100, end] if end == 200 else None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=100,
        has_port=False,
        credits=700,
        holds_free=10,
        cargo_fuel_ore=4,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[101, 102],
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.MOVE
    assert params.get("target_sector") == 200
    assert params.get("urgency") == "cargo_liquidation"


def _setup_three_priced_pairs_for_spread() -> tuple[ProfitablePairsStrategy, GameState]:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    fuel_pair = PortPair(buy_sector=2, sell_sector=3, commodity="fuel_ore", distance=1, path=[2, 3])
    org_pair = PortPair(buy_sector=4, sell_sector=5, commodity="organics", distance=1, path=[4, 5])
    equip_pair = PortPair(buy_sector=6, sell_sector=7, commodity="equipment", distance=1, path=[6, 7])
    strat._pairs = [fuel_pair, org_pair, equip_pair]

    buy_template = SectorInfo(has_port=True, port_class="SSS")
    buy_template.port_status = {"fuel_ore": "selling", "organics": "selling", "equipment": "selling"}
    buy_template.port_prices = {
        "fuel_ore": {"sell": 20},
        "organics": {"sell": 20},
        "equipment": {"sell": 20},
    }
    sell_fuel = SectorInfo(has_port=True, port_class="BSS")
    sell_fuel.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    sell_fuel.port_prices = {"fuel_ore": {"buy": 32}}
    sell_org = SectorInfo(has_port=True, port_class="SBS")
    sell_org.port_status = {"fuel_ore": "selling", "organics": "buying", "equipment": "selling"}
    sell_org.port_prices = {"organics": {"buy": 32}}
    sell_equip = SectorInfo(has_port=True, port_class="SSB")
    sell_equip.port_status = {"fuel_ore": "selling", "organics": "selling", "equipment": "buying"}
    sell_equip.port_prices = {"equipment": {"buy": 32}}

    knowledge._sectors[2] = buy_template
    knowledge._sectors[4] = buy_template.model_copy(deep=True)
    knowledge._sectors[6] = buy_template.model_copy(deep=True)
    knowledge._sectors[3] = sell_fuel
    knowledge._sectors[5] = sell_org
    knowledge._sectors[7] = sell_equip

    def _find_path(src: int, dst: int, max_hops: int | None = None):
        if dst in {2, 4, 6}:
            return [1, dst]
        if src in {2, 4, 6} and dst in {3, 5, 7}:
            return [src, dst]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    state = GameState(context="sector_command", sector=1, credits=3000, holds_total=20, holds_free=20)
    return strat, state


def test_select_best_pair_spread_rotates_after_repeated_fuel_picks() -> None:
    strat, state = _setup_three_priced_pairs_for_spread()

    picks: list[str] = []
    for _ in range(5):
        pair = strat._select_best_pair(state)
        assert pair is not None
        picks.append(str(pair.commodity))

    assert picks[:4] == ["fuel_ore", "fuel_ore", "fuel_ore", "fuel_ore"]
    assert picks[4] == "organics"
    assert strat._last_selected_commodity == "organics"
    assert strat._same_selected_commodity_count == 1


def test_select_best_pair_spread_prefers_equipment_under_combined_pressure() -> None:
    strat, state = _setup_three_priced_pairs_for_spread()

    strat._last_selected_commodity = "organics"
    strat._same_selected_commodity_count = 5
    strat._commodity_failure_streak["fuel_ore"] = 4

    pair = strat._select_best_pair(state)
    assert pair is not None
    assert pair.commodity == "equipment"
    assert strat._last_selected_commodity == "equipment"
    assert strat._same_selected_commodity_count == 1


def test_select_best_pair_deprioritizes_fuel_after_repeated_failures() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    from bbsbot.games.tw2002.strategies.profitable_pairs import PortPair

    fuel_pair = PortPair(buy_sector=2, sell_sector=3, commodity="fuel_ore", distance=1, path=[2, 3])
    org_pair = PortPair(buy_sector=4, sell_sector=5, commodity="organics", distance=1, path=[4, 5])
    strat._pairs = [fuel_pair, org_pair]

    knowledge._sectors[2] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[3] = SectorInfo(has_port=True, port_class="BSS")
    knowledge._sectors[4] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[5] = SectorInfo(has_port=True, port_class="SBS")

    def _find_path(src: int, dst: int, max_hops: int | None = None):
        if dst in {2, 4}:
            return [1, dst]
        if src == 2 and dst == 3:
            return [2, 3]
        if src == 4 and dst == 5:
            return [4, 5]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    state = GameState(context="sector_command", sector=1, credits=350, holds_total=20, holds_free=None)

    first = strat._select_best_pair(state)
    assert first is not None
    assert first.commodity == "fuel_ore"

    strat._commodity_failure_streak["fuel_ore"] = 4
    second = strat._select_best_pair(state)
    assert second is not None
    assert second.commodity == "organics"


def test_local_bootstrap_safe_buy_rotates_off_fuel_after_failures() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = ProfitablePairsStrategy(cfg, knowledge)

    sell_here = SectorInfo(has_port=True, port_class="SSS")
    sell_here.port_status = {"fuel_ore": "selling", "organics": "selling", "equipment": "selling"}
    sell_here.port_prices = {"fuel_ore": {"sell": 20}, "organics": {"sell": 35}}
    sell_here.port_trading_units = {"fuel_ore": 300, "organics": 300}
    knowledge._sectors[50] = sell_here

    fuel_buyer = SectorInfo(has_port=True, port_class="BSS")
    fuel_buyer.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    knowledge._sectors[51] = fuel_buyer

    org_buyer = SectorInfo(has_port=True, port_class="SBS")
    org_buyer.port_status = {"fuel_ore": "selling", "organics": "buying", "equipment": "selling"}
    knowledge._sectors[52] = org_buyer

    knowledge.find_path = lambda start, end, max_hops=100: [50, end] if end in {51, 52} else None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=50,
        credits=600,
        holds_free=12,
        has_port=True,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    action1, params1 = strat._local_bootstrap_trade(state)  # type: ignore[misc]
    assert action1 == TradeAction.TRADE
    assert params1.get("action") == "buy"
    assert params1["opportunity"].commodity == "fuel_ore"

    strat._commodity_failure_streak["fuel_ore"] = 4
    action2, params2 = strat._local_bootstrap_trade(state)  # type: ignore[misc]
    assert action2 == TradeAction.TRADE
    assert params2.get("action") == "buy"
    assert params2["opportunity"].commodity == "organics"
