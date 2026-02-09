"""Screen parsing utilities for TW2002."""

import re

from bbsbot.games.tw2002.logging_utils import logger
from bbsbot.terminal.screen_utils import clean_screen_for_display, extract_menu_options


def extract_semantic_kv(screen: str) -> dict:
    """Extract semantic key/value data from a screen snapshot."""
    data: dict = {}

    # Sector
    sector_matches = re.findall(r"[Ss]ector\s*:\s*(\d+)", screen)
    if sector_matches:
        data["sector"] = int(sector_matches[-1])

    # Warps
    warp_line = None
    for line in screen.splitlines():
        if "Warps to Sector" in line:
            warp_line = line
    if warp_line:
        warps = [int(x) for x in re.findall(r"\d+", warp_line)]
        if warps:
            data["warps"] = warps

    # Ports
    port_match = re.search(r"Ports?\s*:\s*([^,]+),\s*Class\s*\d+\s*\(([^)]+)\)", screen)
    if port_match:
        data["has_port"] = True
        data["port_name"] = port_match.group(1).strip()
        data["port_class"] = port_match.group(2).strip()

    # Planets
    planet_line = None
    for line in screen.splitlines():
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
    credit_match = re.search(r"You have\s+([\d,]+)\s+credits", screen)
    if not credit_match:
        credit_match = re.search(r"You only have\s+([\d,]+)\s+credits", screen, re.IGNORECASE)
    if not credit_match:
        credit_match = re.search(r"Credits?\s*:?\s*([\d,]+)", screen)
    if credit_match:
        data["credits"] = int(credit_match.group(1).replace(",", ""))

    # Fighters
    fighter_match = re.search(r"Fighters\s*:\s*([\d,]+)", screen)
    if fighter_match:
        data["fighters"] = int(fighter_match.group(1).replace(",", ""))

    # Holds
    holds_match = re.search(r"Total Holds\s*:\s*(\d+)", screen)
    if holds_match:
        data["holds_total"] = int(holds_match.group(1))
    empty_match = re.search(r"Empty\s*=\s*(\d+)", screen)
    if empty_match:
        data["holds_free"] = int(empty_match.group(1))
    empty_holds_match = re.search(r"You have\s+(\d+)\s+empty cargo holds", screen)
    if empty_holds_match:
        data["holds_free"] = int(empty_holds_match.group(1))

    # Cargo onboard (port/commodity tables and status screens)
    # Example table row:
    # "Fuel Ore   Buying     820    100%       0"
    # We take the last integer on the line as onboard qty.
    for line in screen.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        lower = line_stripped.lower()
        if lower.startswith("fuel ore"):
            nums = re.findall(r"\b\d+\b", line_stripped)
            if nums:
                data["cargo_fuel_ore"] = int(nums[-1])
        elif lower.startswith("organics"):
            nums = re.findall(r"\b\d+\b", line_stripped)
            if nums:
                data["cargo_organics"] = int(nums[-1])
        elif lower.startswith("equipment"):
            nums = re.findall(r"\b\d+\b", line_stripped)
            if nums:
                data["cargo_equipment"] = int(nums[-1])

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
