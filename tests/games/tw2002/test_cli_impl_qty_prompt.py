# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from bbsbot.games.tw2002.cli_impl import _is_port_qty_prompt


def test_is_port_qty_prompt_only_matches_active_qty_prompt_line() -> None:
    assert _is_port_qty_prompt("How many holds of Fuel Ore do you want to buy [20]?")
    assert _is_port_qty_prompt("How many holds of Organics do you want to sell [9]?   ")
    assert not _is_port_qty_prompt("We'll sell them for 13 credits.")
    assert not _is_port_qty_prompt("Your offer [13] ?")
    assert not _is_port_qty_prompt("")
