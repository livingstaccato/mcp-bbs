from bbsbot.games.tw2002.parsing import extract_semantic_kv


def test_extract_semantic_kv_parses_port_market_table() -> None:
    screen = """
 Items     Status  Trading % of max OnBoard
 -----     ------  ------- -------- -------
Fuel Ore   Buying     820    100%       0
Organics   Buying     970    100%       0
Equipment  Selling   1160    100%       0

You have 300 credits and 20 empty cargo holds.
"""
    data = extract_semantic_kv(screen)

    assert data["port_fuel_ore_status"] == "buying"
    assert data["port_fuel_ore_trading_units"] == 820
    assert data["port_fuel_ore_pct_max"] == 100
    assert data["cargo_fuel_ore"] == 0

    assert data["port_organics_status"] == "buying"
    assert data["port_organics_trading_units"] == 970
    assert data["port_organics_pct_max"] == 100
    assert data["cargo_organics"] == 0

    assert data["port_equipment_status"] == "selling"
    assert data["port_equipment_trading_units"] == 1160
    assert data["port_equipment_pct_max"] == 100
    assert data["cargo_equipment"] == 0
