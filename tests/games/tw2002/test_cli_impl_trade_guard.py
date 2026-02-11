from bbsbot.games.tw2002.cli_impl import _choose_no_trade_guard_action
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


def test_trade_guard_does_not_repeat_local_buy_forever() -> None:
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
        warps=[88, 91, 92],
    )

    action, params = _choose_no_trade_guard_action(state, knowledge, credits_now=300, guard_overage=3) or (None, {})
    assert action == TradeAction.EXPLORE
    assert params["direction"] == 91
