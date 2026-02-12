# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Screen parsing functions - extract game data from screen text."""

from __future__ import annotations

import re


def parse_display_screen(screen: str) -> dict:
    """Parse the output of 'D' (display) command.

    Returns dict with parsed values (may have None for unparsed fields).
    """
    result = {}

    # Credits: "Credits          : 1,234,567"
    credits_match = re.search(r"credits\s*:\s*([\d,]+)", screen, re.IGNORECASE)
    if credits_match:
        result["credits"] = int(credits_match.group(1).replace(",", ""))

    # Turns left: "Turns left       : 500"
    turns_match = re.search(r"turns\s+left\s*:\s*(\d+)", screen, re.IGNORECASE)
    if turns_match:
        result["turns_left"] = int(turns_match.group(1))

    # Fighters: "Fighters         : 100"
    fighters_match = re.search(r"fighters\s*:\s*([\d,]+)", screen, re.IGNORECASE)
    if fighters_match:
        result["fighters"] = int(fighters_match.group(1).replace(",", ""))

    # Shields: "Shields          : 500"
    shields_match = re.search(r"shields\s*:\s*([\d,]+)", screen, re.IGNORECASE)
    if shields_match:
        result["shields"] = int(shields_match.group(1).replace(",", ""))

    # Holds: "Total Holds      : 50" and "Holds w/Goods    : 10"
    total_holds_match = re.search(r"total\s+holds\s*:\s*(\d+)", screen, re.IGNORECASE)
    if total_holds_match:
        result["holds_total"] = int(total_holds_match.group(1))

    holds_used_match = re.search(r"holds\s+w/goods\s*:\s*(\d+)", screen, re.IGNORECASE)
    if holds_used_match and "holds_total" in result:
        result["holds_free"] = result["holds_total"] - int(holds_used_match.group(1))

    # Player name: "Trader Name      : SomeName"
    name_match = re.search(r"(?:trader\s+)?name\s*:\s*(.+)", screen, re.IGNORECASE)
    if name_match:
        result["player_name"] = name_match.group(1).strip()

    # Ship type: "Ship type        : Merchant Cruiser"
    ship_match = re.search(r"ship\s+type\s*:\s*(.+)", screen, re.IGNORECASE)
    if ship_match:
        result["ship_type"] = ship_match.group(1).strip()

    # Ship name: "Your ship        : SS Enterprise" or "Ship             : The Swift Venture"
    # Look for "ship" or "your ship" NOT followed by "type"
    ship_name_match = re.search(r"(?:your\s+)?ship\s*:\s*(.+?)(?:\s*$|\n)", screen, re.IGNORECASE)
    if ship_name_match:
        name = ship_name_match.group(1).strip()
        # Make sure we didn't capture "Ship type" line
        if not name.lower().startswith("type"):
            result["ship_name"] = name

    # Alignment: "Alignment        : 500 (Good)"
    align_match = re.search(r"alignment\s*:\s*(-?\d+)", screen, re.IGNORECASE)
    if align_match:
        result["alignment"] = int(align_match.group(1))

    # Experience: "Experience       : 1000"
    exp_match = re.search(r"experience\s*:\s*([\d,]+)", screen, re.IGNORECASE)
    if exp_match:
        result["experience"] = int(exp_match.group(1).replace(",", ""))

    # Corp: "Corporation      : 1"
    corp_match = re.search(r"corporation\s*:\s*(\d+)", screen, re.IGNORECASE)
    if corp_match:
        result["corp_id"] = int(corp_match.group(1))

    # Current sector: "Current Sector   : 123"
    sector_match = re.search(r"current\s+sector\s*:\s*(\d+)", screen, re.IGNORECASE)
    if sector_match:
        result["sector"] = int(sector_match.group(1))

    return result


def parse_sector_display(screen: str) -> dict:
    """Parse sector display (what you see at sector command prompt).

    Returns dict with sector info.
    """
    result = {
        "warps": [],
        "has_port": False,
        "port_class": None,
        "has_planet": False,
        "planet_names": [],
        "traders_present": [],
        "hostile_fighters": 0,
    }

    # Sector number from prompt: "Command [TL=00:00:00]:[1234] (?=Help)?"
    sector_match = re.search(r"\[(\d+)\]\s*\(\?", screen)
    if sector_match:
        result["sector"] = int(sector_match.group(1))

    # Warps: "Warps to Sector(s) : 1 - 2 - 3" or "Warps to Sector(s) :  (1) - (2)"
    warps_match = re.search(r"warps?\s+to\s+sector\(?s?\)?\s*:\s*(.+)", screen, re.IGNORECASE)
    if warps_match:
        warp_line = warps_match.group(1)
        # Extract all numbers, ignoring parentheses
        warps = re.findall(r"\d+", warp_line)
        result["warps"] = [int(w) for w in warps]

    # Port: "Ports   : Trading Port (BBS)"
    port_match = re.search(r"ports?\s*:\s*(.+)", screen, re.IGNORECASE)
    if port_match:
        port_line = port_match.group(1).strip()
        if port_line and port_line.lower() not in ("none", "-"):
            result["has_port"] = True
            # Extract class: (BBS), (SSB), etc.
            class_match = re.search(r"\(([A-Z]{3})\)", port_line)
            if class_match:
                result["port_class"] = class_match.group(1)

    # Planets: "Planets : Terra (Class M)"
    planet_match = re.search(r"planets?\s*:\s*(.+)", screen, re.IGNORECASE)
    if planet_match:
        planet_line = planet_match.group(1).strip()
        if planet_line and planet_line.lower() not in ("none", "-"):
            result["has_planet"] = True
            # Extract planet names
            names = re.findall(r"([A-Za-z][A-Za-z0-9\s\']+?)(?:\s*\(|,|$)", planet_line)
            result["planet_names"] = [n.strip() for n in names if n.strip()]

    # Traders: "Traders : Captain Bob"
    traders_match = re.search(r"traders?\s*:\s*(.+)", screen, re.IGNORECASE)
    if traders_match:
        trader_line = traders_match.group(1).strip()
        if trader_line and trader_line.lower() not in ("none", "-"):
            # Split by comma or 'and'
            names = re.split(r",|\band\b", trader_line)
            result["traders_present"] = [n.strip() for n in names if n.strip()]

    # Fighters: "Fighters: 1000 (hostile)"
    fighters_match = re.search(r"fighters?\s*:\s*([\d,]+).*hostile", screen, re.IGNORECASE)
    if fighters_match:
        result["hostile_fighters"] = int(fighters_match.group(1).replace(",", ""))

    return result
