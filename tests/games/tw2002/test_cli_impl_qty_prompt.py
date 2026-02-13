# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from bbsbot.games.tw2002.cli_impl import _extract_port_qty_cap, _is_port_qty_prompt


def test_is_port_qty_prompt_only_matches_active_qty_prompt_line() -> None:
    assert _is_port_qty_prompt("How many holds of Fuel Ore do you want to buy [20]?")
    assert _is_port_qty_prompt("How many holds of Organics do you want to sell [9]?   ")
    assert not _is_port_qty_prompt("We'll sell them for 13 credits.")
    assert not _is_port_qty_prompt("Your offer [13] ?")
    assert not _is_port_qty_prompt("")


def test_extract_port_qty_cap_buy_uses_prompt_default() -> None:
    line = "How many holds of Equipment do you want to buy [8]?"
    assert _extract_port_qty_cap(line, "irrelevant", is_sell=False) == 8


def test_extract_port_qty_cap_sell_clamps_to_holds_available() -> None:
    line = "How many holds of Organics do you want to sell [18]?"
    screen = "We are buying up to 920.  You have 2 in your holds."
    assert _extract_port_qty_cap(line, screen, is_sell=True) == 2


def test_extract_port_qty_cap_handles_commas() -> None:
    line = "How many holds of Fuel Ore do you want to sell [1,240]?"
    screen = "We are buying up to 5,000.  You have 980 in your holds."
    assert _extract_port_qty_cap(line, screen, is_sell=True) == 980
