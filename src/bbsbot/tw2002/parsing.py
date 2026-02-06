"""Screen parsing utilities for TW2002."""

import re

from .logging_utils import logger


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


def _clean_screen_for_display(screen: str, max_lines: int = 30) -> list[str]:
    """Clean screen for display by removing padding lines.

    Args:
        screen: Raw screen text
        max_lines: Maximum lines to return

    Returns:
        List of non-empty content lines (up to max_lines)
    """
    lines = []
    for line in screen.split("\n"):
        # Skip pure padding (80+ spaces) and empty lines
        if line.strip() or not line.startswith(" " * 80):
            lines.append(line)
            if len(lines) >= max_lines:
                break
    return lines


def _extract_game_options(screen: str) -> list[tuple[str, str]]:
    """Extract available game options from TWGS menu.

    Args:
        screen: Screen text containing game options

    Returns:
        List of (letter, description) tuples, e.g., [('A', 'My Game'), ('B', 'Game 2')]
    """
    options = []
    # Look for lines like "<A> My Game" or "[A] My Game"
    # Handle cases where multiple games are on the same line like "<A> Game1  <B> Game2"
    pattern = r"[<\[]([A-Z])[>\]]\s+([^<\[\n]+?)(?=\s*[<\[]|$)"
    for match in re.finditer(pattern, screen):
        letter = match.group(1)
        description = match.group(2).strip()
        if description and letter not in ["Q", "X", "!"]:
            options.append((letter, description))

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
