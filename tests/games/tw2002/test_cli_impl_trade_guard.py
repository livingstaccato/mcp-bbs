# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from collections import deque

from bbsbot.games.tw2002.cli_impl import (
    _compute_no_trade_guard_flags,
    _choose_no_trade_guard_action,
    _choose_ping_pong_break_action,
    _get_zero_trade_streak,
    _is_effective_trade_change,
    _is_sector_ping_pong,
    _resolve_no_trade_guard_thresholds,
    _should_count_trade_completion,
    _should_force_bootstrap_trade,
)
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorInfo, SectorKnowledge
from bbsbot.games.tw2002.strategies.base import TradeAction


def test_trade_guard_sells_cargo_at_local_buying_port() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=77,
        has_port=True,
        port_class="BBS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=6,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[10, 11],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.TRADE
    assert params["action"] == "sell"
    assert params["commodity"] == "fuel_ore"
    assert params["max_quantity"] == 6


def test_trade_guard_buys_small_amount_at_local_selling_port() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    knowledge._sectors[90] = SectorInfo(has_port=True, port_class="BBS")

    def _find_path(src: int, dst: int, max_hops: int | None = None):
        if src == 88 and dst == 90:
            return [88, 90]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSB",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[12, 13],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.TRADE
    assert params["action"] == "buy"
    assert params["commodity"] in {"fuel_ore", "organics"}
    assert int(params["max_quantity"]) >= 1


def test_trade_guard_buy_prefers_commodity_with_known_nearby_buyer() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    # Local port sells fuel_ore + organics.
    knowledge._sectors[88] = SectorInfo(has_port=True, port_class="SSB")
    # Only fuel_ore has a known nearby buyer.
    knowledge._sectors[90] = SectorInfo(has_port=True, port_class="BBS")

    def _find_path(src: int, dst: int, max_hops: int | None = None):
        if src == 88 and dst == 90:
            return [88, 90]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSB",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[12, 13],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.TRADE
    assert params["action"] == "buy"
    assert params["commodity"] == "fuel_ore"


def test_trade_guard_avoids_local_buy_when_no_known_buyer_path() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    # Local port sells organics only (from class BSB), but no known organics buyer.
    knowledge._sectors[88] = SectorInfo(has_port=True, port_class="BSB")
    knowledge.find_path = lambda src, dst, max_hops=None: None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="BSB",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[12, 13],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        guard_overage=2,
    ) or (None, {})
    assert action in {TradeAction.MOVE, TradeAction.EXPLORE}
    assert params.get("action") != "buy"


def test_trade_guard_bootstrap_mode_disables_forced_local_buy() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[12, 13],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300, allow_buy=False) or (None, {})
    # With buys disabled and no cargo to sell, guard should reroute/explore.
    assert action in {TradeAction.EXPLORE, TradeAction.MOVE}
    assert params.get("action") != "buy"


def test_trade_guard_moves_to_nearest_known_port_when_not_at_port() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    knowledge._sectors[200] = SectorInfo(has_port=True, port_class="BBS")
    knowledge._sectors[300] = SectorInfo(has_port=True, port_class="SSB")
    knowledge.find_path = lambda start, end, max_hops=100: [100, end] if end == 200 else [100, 150, end]  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=100,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[101, 102],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.MOVE
    assert params["target_sector"] == 200
    assert params["path"] == [100, 200]


def test_trade_guard_uses_direct_jump_path_when_port_path_unknown() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    knowledge._sectors[200] = SectorInfo(has_port=True, port_class="BBS")
    knowledge.find_path = lambda start, end, max_hops=100: None  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=100,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[101, 102],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.MOVE
    assert params["target_sector"] == 200
    assert params["path"] == [100, 200]
    assert params.get("urgency") in {"no_trade_guard", "no_trade_reroute"}


def test_trade_guard_uses_known_local_port_when_state_has_port_is_false() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    info = SectorInfo(has_port=True, port_class="BSS")
    info.port_status = {"fuel_ore": "buying", "organics": "selling", "equipment": "selling"}
    knowledge._sectors[77] = info
    state = GameState(
        context="sector_command",
        sector=77,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=5,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[10, 11],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.TRADE
    assert params["action"] == "sell"
    assert params["commodity"] == "fuel_ore"


def test_trade_guard_explores_when_no_known_port_exists() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=22,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[30, 10, 25],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params["direction"] == 10


def test_trade_guard_hard_probes_trade_when_no_port_intel_and_stalled() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=22,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[30, 10, 25],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        guard_overage=12,
    ) or (None, {})
    assert action == TradeAction.TRADE
    assert params["action"] == "buy"
    assert params["commodity"] in {"fuel_ore", "organics", "equipment"}
    assert int(params["max_quantity"]) == 1
    assert params.get("urgency") == "no_trade_probe"


def test_trade_guard_reroutes_to_any_known_port_when_side_match_unknown() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    knowledge._sectors[200] = SectorInfo(has_port=True, port_class="SSS")

    def _find_path(src: int, dst: int, max_hops: int | None = None):
        if src == 88 and dst == 200:
            return [88, 200]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=3,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[12, 13],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.MOVE
    assert int(params["target_sector"]) == 200
    assert params.get("urgency") == "no_trade_reroute"


def test_trade_guard_forces_escape_jump_after_persistent_stall() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=22,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[30, 10, 25],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        guard_overage=8,
        recent_sectors=[21, 22, 21, 22],
    ) or (None, {})
    assert action == TradeAction.MOVE
    assert params.get("urgency") == "no_trade_escape_jump"
    assert int(params.get("target_sector") or 0) not in {21, 22}
    assert params.get("path", [None])[0] == 22


def test_trade_guard_explore_skips_current_sector_if_present_in_warps() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=131,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[131, 254, 397],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params["direction"] == 254


def test_trade_guard_explore_prefers_not_previous_sector() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=131,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[200, 201],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        previous_sector=200,
    ) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params["direction"] == 201


def test_trade_guard_keeps_local_buy_enabled_after_overage() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    knowledge._sectors[91] = SectorInfo(has_port=True, port_class="BSS")

    def _find_path(src: int, dst: int, max_hops: int | None = None):
        if src == 88 and dst == 91:
            return [88, 91]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[88, 91, 92],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300, guard_overage=3) or (None, {})
    assert action == TradeAction.TRADE
    assert params["action"] == "buy"
    assert int(params["max_quantity"]) >= 1


def test_trade_guard_avoids_empty_hold_sell_probe_when_buys_disabled() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[91, 92, 93],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        allow_buy=False,
        guard_overage=6,
    ) or (None, {})
    # Guard must not force meaningless "sell with empty holds" probes.
    assert action in {TradeAction.EXPLORE, TradeAction.MOVE}
    assert params.get("action") != "sell"


def test_trade_guard_enables_micro_buy_after_persistent_stall_even_when_buys_disabled() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    info = SectorInfo(
        has_port=True,
        port_class="SSS",
        port_status={
            "fuel_ore": "selling",
            "organics": "selling",
            "equipment": "selling",
        },
        port_prices={
            "fuel_ore": {"sell": 40},
            "organics": {"sell": 90},
            "equipment": {"sell": 160},
        },
    )
    knowledge._sectors[88] = info
    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[91, 92, 93],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        allow_buy=False,
        guard_overage=12,
    ) or (None, {})
    assert action == TradeAction.TRADE
    assert params["action"] == "buy"
    assert params["commodity"] == "fuel_ore"
    assert int(params["max_quantity"]) == 1


def test_trade_guard_does_not_force_unaffordable_local_buy() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    info = SectorInfo(
        has_port=True,
        port_class="SSS",
        port_prices={
            "fuel_ore": {"sell": 500},
            "organics": {"sell": 700},
            "equipment": {"sell": 900},
        },
    )
    knowledge._sectors[88] = info
    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[91, 92, 93],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params["direction"] == 91


def test_trade_guard_skips_unknown_price_buy_when_bankroll_is_too_low() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    info = SectorInfo(
        has_port=True,
        port_class="SSS",
        port_status={
            "fuel_ore": "selling",
            "organics": "buying",
            "equipment": "selling",
        },
        # Intentionally omit sell quotes to simulate unknown local prices.
        port_prices={},
    )
    knowledge._sectors[88] = info
    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSS",
        credits=12,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[91, 92, 93],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=12) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params["direction"] == 91


def test_trade_guard_skips_zero_supply_commodities_for_local_buy() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    info = SectorInfo(
        has_port=True,
        port_class="SSS",
        port_status={
            "fuel_ore": "selling",
            "organics": "buying",
            "equipment": "selling",
        },
        port_prices={
            "fuel_ore": {"sell": 10},
            "equipment": {"sell": 5},
        },
        port_trading_units={
            "fuel_ore": 2200,
            "equipment": 0,
        },
    )
    knowledge._sectors[88] = info
    knowledge._sectors[91] = SectorInfo(has_port=True, port_class="BSS")

    def _find_path(src: int, dst: int, max_hops: int | None = None):
        if src == 88 and dst == 91:
            return [88, 91]
        return None

    knowledge.find_path = _find_path  # type: ignore[assignment]
    state = GameState(
        context="sector_command",
        sector=88,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[91, 92, 93],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.TRADE
    assert params["action"] == "buy"
    assert params["commodity"] == "fuel_ore"


def test_trade_guard_preserves_bankroll_when_quote_would_nearly_zero_credits() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    info = SectorInfo(
        has_port=True,
        port_class="SSS",
        port_status={
            "fuel_ore": "selling",
            "organics": "selling",
            "equipment": "selling",
        },
        port_prices={
            "fuel_ore": {"sell": 288},
            "organics": {"sell": 320},
            "equipment": {"sell": 540},
        },
    )
    knowledge._sectors[30] = info
    state = GameState(
        context="sector_command",
        sector=30,
        has_port=True,
        port_class="SSS",
        credits=297,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[91, 92, 93],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=297) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params["direction"] == 91


def test_trade_guard_move_avoids_recent_cycle_targets_when_possible() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    knowledge._sectors[200] = SectorInfo(has_port=True, port_class="BBS")
    knowledge._sectors[300] = SectorInfo(has_port=True, port_class="SSB")
    knowledge.find_path = lambda start, end, max_hops=100: [100, end]  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=100,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[101, 102],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        recent_sectors=[200, 100, 200, 100],
    ) or (None, {})
    assert action == TradeAction.MOVE
    assert params["target_sector"] == 300


def test_trade_guard_prefers_port_that_buys_held_cargo_when_rerouting() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    # Nearest port does not buy equipment (BBS => equipment selling).
    knowledge._sectors[200] = SectorInfo(has_port=True, port_class="BBS")
    # Farther port buys equipment (BSB => equipment buying).
    knowledge._sectors[300] = SectorInfo(has_port=True, port_class="BSB")
    knowledge.find_path = lambda start, end, max_hops=100: [100, end] if end == 200 else [100, 150, end]  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=100,
        has_port=False,
        port_class=None,
        credits=300,
        holds_free=19,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=1,
        warps=[101, 102],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300) or (None, {})
    assert action == TradeAction.MOVE
    assert params["target_sector"] == 300


def test_trade_guard_local_nonbuyer_reroutes_instead_of_forcing_bad_sell_probe() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    knowledge._sectors[77] = SectorInfo(has_port=True, port_class="SSS")
    knowledge._sectors[300] = SectorInfo(has_port=True, port_class="BSB")
    knowledge.find_path = lambda start, end, max_hops=100: [77, end]  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=77,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=19,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=1,
        warps=[80, 81],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        allow_buy=False,
        guard_overage=8,
    ) or (None, {})
    assert action == TradeAction.MOVE
    assert params["target_sector"] == 300


def test_trade_guard_nonbuyer_falls_back_to_any_known_port_when_no_matching_buyer_known() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    # Current port sells everything (does not buy equipment we hold).
    knowledge._sectors[77] = SectorInfo(has_port=True, port_class="SSS")
    # Known port also does not buy equipment.
    knowledge._sectors[200] = SectorInfo(has_port=True, port_class="BBS")
    knowledge.find_path = lambda start, end, max_hops=100: [77, end]  # type: ignore[assignment]

    state = GameState(
        context="sector_command",
        sector=77,
        has_port=True,
        port_class="SSS",
        credits=300,
        holds_free=19,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=1,
        warps=[81, 82],
    )

    action, params = _choose_no_trade_guard_action(
        state,
        knowledge,
        credits_now=300,
        allow_buy=False,
        guard_overage=8,
    ) or (None, {})
    assert action == TradeAction.MOVE
    assert int(params.get("target_sector") or 0) == 200


def test_sector_ping_pong_detector_identifies_abab_pattern() -> None:
    assert _is_sector_ping_pong([10, 20, 10, 20]) is True
    assert _is_sector_ping_pong([10, 20, 30, 20]) is False


def test_sector_ping_pong_detector_identifies_abcabc_pattern() -> None:
    assert _is_sector_ping_pong([239, 498, 503, 239, 498, 503]) is True


def test_ping_pong_break_forces_alternate_explore_target() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=20,
        has_port=False,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[10, 30],
    )
    recent = deque([10, 20, 10, 20], maxlen=8)

    action, params = _choose_ping_pong_break_action(
        state=state,
        knowledge=knowledge,
        recent_sectors=recent,
        turns_since_last_trade=15,
    ) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params.get("direction") == 30
    assert params.get("urgency") == "loop_break"


def test_ping_pong_break_avoids_recent_cycle_nodes_when_possible() -> None:
    knowledge = SectorKnowledge(knowledge_dir=None, character_name="t")
    state = GameState(
        context="sector_command",
        sector=503,
        has_port=False,
        credits=300,
        holds_free=20,
        cargo_fuel_ore=0,
        cargo_organics=0,
        cargo_equipment=0,
        warps=[239, 498, 700],
    )
    recent = deque([239, 498, 503, 239, 498, 503], maxlen=8)

    action, params = _choose_ping_pong_break_action(
        state=state,
        knowledge=knowledge,
        recent_sectors=recent,
        turns_since_last_trade=15,
    ) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params.get("direction") == 700


def test_dynamic_guard_relaxes_for_profitable_high_trade_rate() -> None:
    cfg = BotConfig()
    guard_turns, stale_turns, stale_enabled = _resolve_no_trade_guard_thresholds(
        config=cfg,
        turns_used=500,
        turns_since_last_trade=18,
        trades_done=42,
        credits_per_turn=0.9,
        trades_per_100_turns=8.4,
    )
    assert guard_turns > int(cfg.trading.no_trade_guard_turns)
    assert stale_turns > int(cfg.trading.no_trade_guard_stale_turns)
    assert stale_enabled is False


def test_dynamic_guard_tightens_for_unprofitable_stalled_bot() -> None:
    cfg = BotConfig()
    guard_turns, stale_turns, stale_enabled = _resolve_no_trade_guard_thresholds(
        config=cfg,
        turns_used=80,
        turns_since_last_trade=70,
        trades_done=0,
        credits_per_turn=-0.6,
        trades_per_100_turns=0.3,
    )
    assert guard_turns < int(cfg.trading.no_trade_guard_turns)
    assert stale_turns < int(cfg.trading.no_trade_guard_stale_turns)
    assert stale_enabled is True


def test_dynamic_guard_reenables_stale_after_long_drought() -> None:
    cfg = BotConfig()
    guard_turns, stale_turns, stale_enabled = _resolve_no_trade_guard_thresholds(
        config=cfg,
        turns_used=900,
        turns_since_last_trade=220,
        trades_done=25,
        credits_per_turn=0.4,
        trades_per_100_turns=3.2,
    )
    assert guard_turns >= int(cfg.trading.no_trade_guard_turns)
    assert stale_turns >= int(cfg.trading.no_trade_guard_stale_turns)
    assert stale_enabled is True


def test_guard_flags_hold_off_stale_force_for_healthy_traders() -> None:
    cfg = BotConfig()
    cfg.trading.no_trade_guard_stale_soft_holdoff = True
    cfg.trading.no_trade_guard_stale_soft_holdoff_multiplier = 2.2
    force_guard, force_action, stale_holdoff = _compute_no_trade_guard_flags(
        config=cfg,
        turns_used=260,
        turns_since_last_trade=70,
        trades_done=9,
        guard_min_trades=1,
        guard_turns=45,
        guard_stale_turns=45,
        stale_guard_enabled=True,
        credits_per_turn=0.25,
        trades_per_100_turns=3.0,
        last_stale_force_turn=250,
    )
    assert stale_holdoff is True
    assert force_guard is False
    assert force_action is False


def test_guard_flags_throttle_stale_force_action_interval() -> None:
    cfg = BotConfig()
    cfg.trading.no_trade_guard_stale_force_interval_turns = 4
    force_guard, force_action, stale_holdoff = _compute_no_trade_guard_flags(
        config=cfg,
        turns_used=100,
        turns_since_last_trade=80,
        trades_done=1,
        guard_min_trades=1,
        guard_turns=45,
        guard_stale_turns=45,
        stale_guard_enabled=True,
        credits_per_turn=-0.3,
        trades_per_100_turns=0.5,
        last_stale_force_turn=98,
    )
    assert stale_holdoff is False
    assert force_guard is True
    assert force_action is False


def test_get_zero_trade_streak_returns_exact_signature_when_present() -> None:
    class _Bot:
        _zero_trade_streak = {(447, "fuel_ore", "sell"): 3, (447, "organics", "buy"): 1}

    bot = _Bot()
    assert _get_zero_trade_streak(bot, 447, "fuel_ore", "sell") == 3
    assert _get_zero_trade_streak(bot, 447, "organics", "buy") == 1


def test_get_zero_trade_streak_returns_sector_max_for_fallback() -> None:
    class _Bot:
        _zero_trade_streak = {(447, "fuel_ore", "sell"): 2, (447, "", ""): 5, (71, "fuel_ore", "sell"): 4}

    bot = _Bot()
    assert _get_zero_trade_streak(bot, 447) == 5
    assert _get_zero_trade_streak(bot, 71) == 4


def test_should_force_bootstrap_trade_after_threshold_before_guard() -> None:
    cfg = BotConfig()
    cfg.trading.bootstrap_trade_turns = 12
    assert (
        _should_force_bootstrap_trade(
            config=cfg,
            turns_used=12,
            trades_done=0,
            guard_min_trades=1,
            force_guard=False,
        )
        is True
    )


def test_should_not_force_bootstrap_trade_when_guard_active_or_trade_done() -> None:
    cfg = BotConfig()
    cfg.trading.bootstrap_trade_turns = 12
    assert (
        _should_force_bootstrap_trade(
            config=cfg,
            turns_used=20,
            trades_done=0,
            guard_min_trades=1,
            force_guard=True,
        )
        is False
    )
    assert (
        _should_force_bootstrap_trade(
            config=cfg,
            turns_used=20,
            trades_done=1,
            guard_min_trades=1,
            force_guard=False,
        )
        is False
    )


def test_is_effective_trade_change_is_directional() -> None:
    assert _is_effective_trade_change(credit_change=-40, trade_action="buy") is True
    assert _is_effective_trade_change(credit_change=40, trade_action="buy") is False
    assert _is_effective_trade_change(credit_change=40, trade_action="sell") is True
    assert _is_effective_trade_change(credit_change=-40, trade_action="sell") is False
    assert _is_effective_trade_change(credit_change=12, trade_action=None) is True


def test_should_count_trade_completion_only_for_effective_execution() -> None:
    assert _should_count_trade_completion(trade_interaction_seen=True, credit_change=0) is False
    assert _should_count_trade_completion(trade_interaction_seen=False, credit_change=35, trade_action="sell") is True
    assert _should_count_trade_completion(trade_interaction_seen=False, credit_change=-35, trade_action="sell") is False
    assert _should_count_trade_completion(trade_interaction_seen=False, credit_change=0) is False
