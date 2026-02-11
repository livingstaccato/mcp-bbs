from bbsbot.games.tw2002.strategies.ai.decision_maker import _json_safe
from bbsbot.games.tw2002.strategies.base import TradeOpportunity


def test_json_safe_serializes_trade_opportunity() -> None:
    params = {
        "opportunity": TradeOpportunity(
            buy_sector=10,
            sell_sector=20,
            commodity="fuel_ore",
            expected_profit=150,
            distance=2,
        ),
        "count": 1,
    }

    safe = _json_safe(params)
    assert isinstance(safe, dict)
    assert isinstance(safe["opportunity"], dict)
    assert safe["opportunity"]["commodity"] == "fuel_ore"
    assert safe["opportunity"]["buy_sector"] == 10
    assert safe["count"] == 1
