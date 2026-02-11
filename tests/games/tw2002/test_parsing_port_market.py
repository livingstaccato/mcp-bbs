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
    assert data["credits"] == 300


def test_extract_semantic_kv_parses_ship_stats_and_turns() -> None:
    screen = """
One turn deducted, 65,487 turns left.
Trader Name    : Lance Corporal CmdrTest
Ship Type      : Merchant Cruiser
Total Holds    : 20 - Fuel Ore=1 Equipment=2 Empty=17
Fighters       : 30
Shields        : 12
You have 2,223 credits and 18 empty cargo holds.
"""
    data = extract_semantic_kv(screen)

    assert data["turns_left"] == 65487
    assert data["player_name"] == "Lance Corporal CmdrTest"
    assert data["ship_type"] == "Merchant Cruiser"
    assert data["holds_total"] == 20
    assert data["fighters"] == 30
    assert data["shields"] == 12
    assert data["credits"] == 2223


def test_extract_semantic_kv_uses_owned_fighters_not_price() -> None:
    screen = """
Commerce report for: 02:09:47 PM Mon Feb 09, 2054
You can buy:
A  Cargo holds     :    594 credits / next hold                0
B  Fighters        :    237 credits per fighter                1
C  Shield Points   :    112 credits per point                  2
"""
    data = extract_semantic_kv(screen)

    assert data["fighters"] == 1
    assert data["shields"] == 2


def test_extract_semantic_kv_parses_slash_quick_stats_line() -> None:
    screen = """
Command [TL=00:00:00]:[599] (?=Help)? :
Sect 599³Turns 65,520³Creds 300³Figs 30³Shlds 0³Hlds 20³Ore 0³Org 0³Equ 0
Col 0³Phot 0³Armd 0³Lmpt 0³GTorp 0³TWarp No³Clks 0³Beacns 0³AtmDt 0³Crbo 0
EPrb 0³MDis 0³PsPrb No³PlScn No³LRS None³Aln 1³Exp 1³Ship 1 MerCru
"""
    data = extract_semantic_kv(screen)

    assert data["sector"] == 599
    assert data["turns_left"] == 65520
    assert data["credits"] == 300
    assert data["fighters"] == 30
    assert data["shields"] == 0
    assert data["holds_total"] == 20
    assert data["holds_free"] == 20
    assert data["cargo_fuel_ore"] == 0
    assert data["cargo_organics"] == 0
    assert data["cargo_equipment"] == 0
    assert data["alignment"] == 1
    assert data["experience"] == 1
    assert data["ship_type"] == "MerCru"


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
