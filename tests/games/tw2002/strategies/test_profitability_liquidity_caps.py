from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge, SectorInfo
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

