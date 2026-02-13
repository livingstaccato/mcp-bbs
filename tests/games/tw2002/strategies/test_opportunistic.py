# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorInfo, SectorKnowledge
from bbsbot.games.tw2002.strategies.base import TradeAction
from bbsbot.games.tw2002.strategies.opportunistic import OpportunisticStrategy


def test_max_wander_forces_exploration() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = OpportunisticStrategy(cfg, knowledge)

    # Simulate a long no-trade streak.
    limit = int(cfg.trading.opportunistic.max_wander_without_trade)
    strat._exploration.wanders_without_trade = limit

    state = GameState(
        context="sector_command",
        sector=10,
        credits=300,
        has_port=False,
        warps=[20, 30, 40],
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.EXPLORE
    assert params.get("direction") in {20, 30, 40}
    # Counter should reset when we trigger forced exploration.
    assert strat._exploration.wanders_without_trade == 0


def test_max_wander_preempts_known_wander_move() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = OpportunisticStrategy(cfg, knowledge)

    # Build known port candidates so normal behavior would choose MOVE.
    knowledge._sectors[20] = SectorInfo(has_port=True, port_class="BBS")
    knowledge.find_path = lambda src, dst, max_hops=None: [src, dst]  # type: ignore[assignment]

    limit = int(cfg.trading.opportunistic.max_wander_without_trade)
    strat._exploration.wanders_without_trade = limit

    state = GameState(
        context="sector_command",
        sector=10,
        credits=300,
        has_port=False,
        warps=[20, 30],
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.EXPLORE
    assert params.get("direction") in {20, 30}


def test_wander_prefers_seller_ports_when_no_cargo() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = OpportunisticStrategy(cfg, knowledge)

    # Buyer-only port should be skipped when we have empty holds.
    knowledge._sectors[20] = SectorInfo(has_port=True, port_class="BBB")
    # Seller-capable port should be preferred.
    knowledge._sectors[30] = SectorInfo(has_port=True, port_class="SSB")

    state = GameState(
        context="sector_command",
        sector=10,
        credits=300,
        has_port=False,
        warps=[20, 30],
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    target = strat._pick_wander_target(state)
    assert target == 30


def test_opportunistic_local_sell_includes_action_and_quantity() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = OpportunisticStrategy(cfg, knowledge)

    state = GameState(
        context="sector_command",
        sector=7,
        credits=300,
        has_port=True,
        port_class="BSS",
        warps=[9],
        cargo_fuel_ore=4,
        cargo_organics=0,
        cargo_equipment=0,
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.TRADE
    assert params.get("action") == "sell"
    assert int(params.get("max_quantity", 0)) == 4


def test_opportunistic_local_buy_includes_action_and_quantity() -> None:
    cfg = BotConfig()
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    strat = OpportunisticStrategy(cfg, knowledge)

    # Current port sells fuel ore, nearby sector buys it.
    knowledge._sectors[10] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[11] = SectorInfo(has_port=True, port_class="BSS")
    knowledge.find_path = lambda src, dst, max_hops=None: [src, dst] if dst == 11 else None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=10,
        credits=700,
        has_port=True,
        port_class="SSS",
        holds_total=20,
        holds_free=None,
        warps=[11],
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
    )

    action, params = strat.get_next_action(state)
    assert action == TradeAction.TRADE
    assert params.get("action") == "buy"
    assert int(params.get("max_quantity", 0)) >= 1
