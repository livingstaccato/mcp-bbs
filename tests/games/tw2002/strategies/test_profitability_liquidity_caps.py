from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge, SectorInfo
from bbsbot.games.tw2002.strategies.profitable_pairs import ProfitablePairsStrategy
from bbsbot.games.tw2002.strategies.base import TradeAction


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
