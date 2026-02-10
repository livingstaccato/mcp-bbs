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


def test_extract_semantic_kv_marks_no_port_when_explicitly_reported() -> None:
    screen = """
Command [TL=00:00:00]:[673] (?=Help)? : P
There is no port in this sector!
Sector : 673 in uncharted space.
Warps to Sector(s) : 107 - 211 - 453 - 456 - 899 - 961
Command [TL=00:00:00]:[673] (?=Help)? :
"""
    data = extract_semantic_kv(screen)
    assert data["sector"] == 673
    assert data["has_port"] is False
    assert data["port_class"] is None


def test_extract_semantic_kv_ignores_stale_port_lines_from_scrollback() -> None:
    screen = """
Sector : 665 in uncharted space.
Ports   : Tenelphi, Class 5 (SBS)
Warps to Sector(s) : 220 - 502 - 673 - 837 - 848
Command [TL=00:00:00]:[665] (?=Help)? : 673
Warping to Sector 673
Sector : 673 in uncharted space.
Warps to Sector(s) : 107 - (211) - (453) - (456) - 899 - (961)
Command [TL=00:00:00]:[673] (?=Help)? : P
There is no port in this sector!
Command [TL=00:00:00]:[673] (?=Help)? :
"""
    data = extract_semantic_kv(screen)
    assert data["sector"] == 673
    assert data["has_port"] is False
    assert data.get("port_name") is None
    assert data.get("port_class") is None
