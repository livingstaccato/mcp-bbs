# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Screen parsing utilities for TW2002."""

import re

from bbsbot.games.tw2002.logging_utils import logger
from bbsbot.terminal.screen_utils import clean_screen_for_display, extract_menu_options


def _tail_for_current_prompt(screen: str) -> str:
    """Return a tail slice of the screen anchored near the *current* prompt/sector block.

    TW2002 screens often include scrollback from previous sectors. If we regex the entire
    buffer, we can accidentally "learn" stale `Ports:` lines and poison knowledge.
    Anchoring near the last prompt/sector line keeps extraction aligned with what the
    player is currently seeing.
    """
    if not screen:
        return ""

    anchors: list[int] = []
    for pat in (
        r"(?im)^\s*Command\s*\[TL=.*\]:\[\d+\]\s*\(\?=Help\)\?\s*:\s*$",
        r"(?im)^\s*Sector\s*:\s*\d+",
    ):
        for m in re.finditer(pat, screen):
            anchors.append(m.start())

    if not anchors:
        return screen

    anchor = max(anchors)
    # Include a little context before the anchor line in case `Ports:` is printed
    # just above the prompt/sector line.
    return screen[max(0, anchor - 900) :]


def extract_semantic_kv(screen: str) -> dict:
    """Extract semantic key/value data from a screen snapshot."""
    data: dict = {}
    tail = _tail_for_current_prompt(screen)
    semantic_text = tail or screen

    # Sector
    sector_matches = re.findall(r"[Ss]ector\s*:\s*(\d+)", tail)
    if sector_matches:
        data["sector"] = int(sector_matches[-1])

    # Warps
    warp_line = None
    for line in tail.splitlines():
        if "Warps to Sector" in line:
            warp_line = line
    if warp_line:
        warps = [int(x) for x in re.findall(r"\d+", warp_line)]
        if warps:
            data["warps"] = warps

    # Ports
    tail_lower = tail.lower()
    # Explicit negative signal (e.g. after sending 'P' in an empty sector)
    if "no port in this sector" in tail_lower:
        data["has_port"] = False
        data["port_name"] = None
        data["port_class"] = None
    else:
        # Prefer the last Ports: line near the current prompt; older ports in scrollback
        # should not be considered relevant to the current sector.
        port_value: str | None = None
        for line in tail.splitlines():
            if re.search(r"(?i)^\s*ports?\s*:", line):
                port_value = line.split(":", 1)[-1].strip()
        if port_value is not None:
            if not port_value or port_value.strip().lower() in ("none", "-"):
                data["has_port"] = False
                data["port_name"] = None
                data["port_class"] = None
            else:
                data["has_port"] = True
                # Common formats:
                # - "Trading Port (BBS)"
                # - "<Name>, Class 5 (SBB)"
                # - "<Name> (BBS)"
                if class_match := re.search(r"\(([A-Z]{3})\)", port_value):
                    data["port_class"] = class_match.group(1).strip().upper()
                # Name heuristics: strip trailing ", Class ..." and "(BBS)".
                name = re.sub(r",\s*Class\s*\d+\s*\([A-Z]{3}\)\s*$", "", port_value, flags=re.IGNORECASE)
                name = re.sub(r"\s*\([A-Z]{3}\)\s*$", "", name).strip()
                if name:
                    data["port_name"] = name

    # Planets
    planet_line = None
    for line in tail.splitlines():
        if line.strip().startswith("Planets"):
            planet_line = line
    if planet_line:
        # Example: "Planets : (M) Codex Terra"
        names = []
        for match in re.finditer(r"\)\s*([^()]+)", planet_line):
            name = match.group(1).strip()
            if name:
                names.append(name)
        if names:
            data["has_planet"] = True
            data["planet_names"] = names

    # Credits
    credit_match = re.search(
        r"(?im)^\s*you (?:only )?have\s+([\d,]+)\s+credits(?:\b|[^\w])",
        semantic_text,
    )
    if not credit_match:
        # Strict "Credits: 123" style lines only. Avoid poisoning bankroll from:
        # - "237 credits per fighter"
        # - "594 credits / next hold"
        credit_match = re.search(
            r"(?im)^\s*credits(?!\s*(?:per|/))\s*:?\s*([\d,]+)\s*$",
            semantic_text,
        )
    if credit_match:
        data["credits"] = int(credit_match.group(1).replace(",", ""))

    # Banked credits (when on banking-related screens).
    bank_match = re.search(
        r"(?im)^\s*you have\s+([\d,]+)\s+credits?\s+in\s+the\s+bank\b",
        semantic_text,
    )
    if not bank_match:
        bank_match = re.search(
            r"(?im)\bbank(?:\s+account)?(?:\s+balance)?\s*:?\s*([\d,]+)\s*credits?\b",
            semantic_text,
        )
    if bank_match:
        data["bank_balance"] = int(bank_match.group(1).replace(",", ""))

    # Quick-stats line from "/" command, e.g.:
    # "Sect 599³Turns 65,520³Creds 300³Figs 30³Shlds 0³Hlds 20³Ore 0³Org 0³Equ 0 ..."
    # The separator is often CP437 vertical line rendered as "³".
    quick_text = semantic_text.replace("³", " ").replace("|", " ")
    if "sect" in quick_text.lower() and "creds" in quick_text.lower():
        quick_map = {
            "Sect": "sector",
            "Turns": "turns_left",
            "Creds": "credits",
            "Figs": "fighters",
            "Shlds": "shields",
            "Hlds": "holds_total",
            "Ore": "cargo_fuel_ore",
            "Org": "cargo_organics",
            "Equ": "cargo_equipment",
            "Aln": "alignment",
            "Exp": "experience",
        }
        for token, field in quick_map.items():
            m = re.search(rf"(?i)\b{re.escape(token)}\s+([\d,]+)\b", quick_text)
            if not m:
                continue
            data[field] = int(m.group(1).replace(",", ""))

        # Ship shorthand often appears as "Ship 1 MerCru".
        if ship_quick_match := re.search(r"(?i)\bship\s+\d+\s+([A-Za-z0-9_]+)", quick_text):
            data["ship_type"] = ship_quick_match.group(1).strip()

        # Derive free holds from quick cargo breakdown when available.
        try:
            if data.get("holds_total") is not None:
                ore = int(data.get("cargo_fuel_ore") or 0)
                org = int(data.get("cargo_organics") or 0)
                equ = int(data.get("cargo_equipment") or 0)
                used = max(0, ore + org + equ)
                data["holds_free"] = max(0, int(data["holds_total"]) - used)
        except Exception:
            pass

    # Turns left
    turns_match = re.search(r"([\d,]+)\s+turns\s+left", semantic_text, re.IGNORECASE)
    if not turns_match:
        turns_match = re.search(r"(?im)^\s*turns(?:\s+left)?\s*:\s*([\d,]+)\s*$", semantic_text)
    if turns_match:
        data["turns_left"] = int(turns_match.group(1).replace(",", ""))

    # Player / ship identity
    if trader_name_match := re.search(r"(?im)^\s*trader\s+name\s*:\s*(.+?)\s*$", semantic_text):
        data["player_name"] = trader_name_match.group(1).strip()
    if ship_type_match := re.search(r"(?im)^\s*ship\s+type\s*:\s*(.+?)\s*$", semantic_text):
        data["ship_type"] = ship_type_match.group(1).strip()
    if ship_name_match := re.search(r"(?im)^\s*(?:your\s+)?ship\s*:\s*(.+?)\s*$", semantic_text):
        ship_name = ship_name_match.group(1).strip()
        if ship_name and not ship_name.lower().startswith("type"):
            data["ship_name"] = ship_name

    # Player progression
    if alignment_match := re.search(r"(?im)^\s*alignment\s*:\s*(-?\d+)\s*$", semantic_text):
        data["alignment"] = int(alignment_match.group(1))
    if experience_match := re.search(r"(?im)^\s*experience\s*:\s*([\d,]+)\s*$", semantic_text):
        data["experience"] = int(experience_match.group(1).replace(",", ""))
    if corp_match := re.search(r"(?im)^\s*corporation\s*:\s*(\d+)\s*$", semantic_text):
        data["corp_id"] = int(corp_match.group(1))

    # Fighters
    fighter_match = re.search(
        r"(?im)^\s*(?:[A-Z]\s+)?fighters\s*:\s*(?:[\d,]+\s+credits\s+per\s+fighter\s+)?([\d,]+)\s*$",
        semantic_text,
    )
    if fighter_match:
        data["fighters"] = int(fighter_match.group(1).replace(",", ""))

    # Shields
    shield_match = re.search(
        r"(?im)^\s*(?:[A-Z]\s+)?shields?\s*:\s*(?:[\d,]+\s+credits\s+per\s+point\s+)?([\d,]+)\s*$",
        semantic_text,
    )
    if not shield_match:
        shield_match = re.search(
            r"(?im)^\s*(?:[A-Z]\s+)?shield\s+points?\s*:\s*(?:[\d,]+\s+credits\s+per\s+point\s+)?([\d,]+)\s*$",
            semantic_text,
        )
    if shield_match:
        data["shields"] = int(shield_match.group(1).replace(",", ""))

    # Holds
    holds_match = re.search(r"Total Holds\s*:\s*(\d+)", semantic_text)
    if holds_match:
        data["holds_total"] = int(holds_match.group(1))
    empty_match = re.search(r"Empty\s*=\s*(\d+)", semantic_text)
    if empty_match:
        data["holds_free"] = int(empty_match.group(1))
    empty_holds_match = re.search(r"You have\s+(\d+)\s+empty cargo holds", semantic_text)
    if empty_holds_match:
        data["holds_free"] = int(empty_holds_match.group(1))

    # Cargo onboard (port/commodity tables and status screens)
    # Use cleaned display text to avoid ANSI artifacts.
    plain_lines = clean_screen_for_display(semantic_text)
    # screen_utils.clean_screen_for_display returns list[str]
    iter_lines = plain_lines if isinstance(plain_lines, list) else str(plain_lines).splitlines()
    for line in iter_lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if re.search(r"(?i)\btotal\s+holds\b", line_stripped):
            for commodity, label in (("fuel_ore", "fuel ore"), ("organics", "organics"), ("equipment", "equipment")):
                match = re.search(rf"(?i)\b{re.escape(label)}\s*=\s*([\d,]+)", line_stripped)
                if match:
                    data[f"cargo_{commodity}"] = int(match.group(1).replace(",", ""))

    # Quantity prompt context:
    # "We are buying up to 2230.  You have 3 in your holds."
    # "How many holds of Fuel Ore do you want to sell [3]?"
    qty_prompt_re = re.compile(
        r"(?i)how\s+many\s+holds\s+of\s+(fuel\s+ore|organics|equipment)\s+do\s+you\s+want\s+to\s+(buy|sell)\s*\[[\d,]+\]\s*\?"
    )
    holds_re = re.compile(r"(?i)\byou have\s+([\d,]+)\s+in your holds\b")
    commodity_map = {"fuel ore": "fuel_ore", "organics": "organics", "equipment": "equipment"}
    for idx, line in enumerate(iter_lines):
        m_qty = qty_prompt_re.search(line.strip())
        if not m_qty:
            continue
        commodity = commodity_map.get(m_qty.group(1).lower().strip())
        if not commodity:
            continue
        nearby = "\n".join(iter_lines[max(0, idx - 3) : idx + 1])
        m_holds = holds_re.search(nearby)
        if m_holds:
            data[f"cargo_{commodity}"] = int(m_holds.group(1).replace(",", ""))

    # Port report market table (supply/demand + indicative price)
    # Header:
    # "Items     Status  Trading % of max OnBoard"
    # Rows:
    # "Fuel Ore   Buying     820    100%       0"
    port_header_seen = any(
        re.search(r"(?i)\bitems\b.*\bstatus\b.*\btrading\b.*%\s*of\s*max\b.*\bonboard\b", line)
        for line in iter_lines
    )
    if port_header_seen:
        data["has_port"] = True
        row_re = re.compile(
            r"^(Fuel\s+Ore|Organics|Equipment)\s+(Buying|Selling)\s+([\d,]+)\s+(\d+)%\s+([\d,]+)\s*$",
            re.IGNORECASE,
        )
        item_map = {
            "fuel ore": "fuel_ore",
            "organics": "organics",
            "equipment": "equipment",
        }
        for line in iter_lines:
            m = row_re.match(line.strip())
            if not m:
                continue
            item = m.group(1).lower().strip()
            status = m.group(2).lower().strip()  # buying|selling
            units = int(m.group(3).replace(",", ""))
            pct = int(m.group(4))
            # onboard already handled, but keep parsing consistent
            onboard = int(m.group(5).replace(",", ""))
            commodity = item_map.get(item)
            if not commodity:
                continue
            data[f"port_{commodity}_status"] = status
            data[f"port_{commodity}_trading_units"] = units
            data[f"port_{commodity}_pct_max"] = pct
            # Ensure cargo is also present if we saw this row.
            data[f"cargo_{commodity}"] = onboard

    return data


def _parse_credits_from_screen(bot, screen: str) -> int:
    """Extract credit amount from screen text.

    Args:
        bot: TradingBot instance
        screen: Screen text to parse

    Returns:
        Credit amount extracted, or current credits if not found
    """
    # Look for patterns like "Credits: 1,000,000" or "Credits: 1000000"
    match = re.search(r"Credits?:?\s*(\d{1,3}(?:,\d{3})*|\d+)", screen)
    if match:
        credit_str = match.group(1).replace(",", "")
        return int(credit_str)
    return bot.current_credits


def _parse_sector_from_screen(bot, screen: str) -> int:
    """Extract current sector from screen text.

    Args:
        bot: TradingBot instance
        screen: Screen text to parse

    Returns:
        Sector number extracted, or current sector if not found
    """
    # Look for "Sector ###" or "Sector: ###"
    match = re.search(r"[Ss]ector\s*:?\s*(\d+)", screen)
    if match:
        return int(match.group(1))
    return bot.current_sector or 0


# Re-export framework utility with tw2002-specific alias
_clean_screen_for_display = clean_screen_for_display


def _extract_game_options(screen: str) -> list[tuple[str, str]]:
    """Extract available game options from TWGS menu.

    Args:
        screen: Screen text containing game options

    Returns:
        List of (letter, description) tuples, e.g., [('A', 'My Game'), ('B', 'Game 2')]
    """
    # Use framework menu extraction
    options = extract_menu_options(screen)

    # Filter out common exit keys (tw2002-specific logic)
    options = [(letter, desc) for letter, desc in options if letter not in ["Q", "X", "!"]]

    # DEBUG: Log what we found
    if not options and ("<" in screen or "[" in screen):
        logger.warning("game_options_extraction_failed", found_zero_options=True, screen_has_brackets=True)

    return options


def _select_trade_wars_game(screen: str) -> str:
    """Select the Trade Wars game from available options.

    Args:
        screen: Screen text containing game options

    Returns:
        Letter of the game to select (e.g., 'B')
    """
    options = _extract_game_options(screen)
    if not options:
        print("  ⚠️  No game options found, defaulting to 'B'")
        return "B"

    print(f"  Available games: {options}")

    # Look for "Apocalypse" - often Trade Wars in this BBS
    for letter, desc in options:
        if "apocalypse" in desc.lower():
            print(f"  → Found Apocalypse game: {letter} ({desc})")
            return letter

    # Look for "AI Game" - often Trade Wars is labeled this way
    for letter, desc in options:
        if "ai" in desc.lower():
            print(f"  → Found AI Game (likely TW): {letter} ({desc})")
            return letter

    # Look for "Trade Wars" in the descriptions
    for letter, desc in options:
        if "trade" in desc.lower() or "tw" in desc.lower():
            print(f"  → Found Trade Wars game: {letter} ({desc})")
            return letter

    # If no Trade Wars found, try second option (B is often the real game)
    if len(options) > 1:
        letter, desc = options[1]
        print(f"  → Using second option: {letter} ({desc})")
        return letter

    # Fall back to first option
    letter, desc = options[0]
    print(f"  → Using first available game: {letter} ({desc})")
    return letter
