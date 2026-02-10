"""Port validation and data extraction for trading operations."""

from __future__ import annotations

import re

from bbsbot.games.tw2002.parsing import extract_semantic_kv
from bbsbot.logging import get_logger

logger = get_logger(__name__)


def validate_kv_data(kv_data: dict | None, prompt_id: str) -> tuple[bool, str]:
    """Validate extracted K/V data before using.

    Args:
        kv_data: Extracted K/V data from prompt detection
        prompt_id: The detected prompt ID

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not kv_data:
        return True, ""  # No data to validate

    # Check validation status
    validation = kv_data.get("_validation", {})
    if not validation.get("valid", True):
        errors = validation.get("errors", ["Unknown validation error"])
        return False, f"Validation failed for {prompt_id}: {errors[0]}"

    # Check for sector validity if present
    if "sector" in kv_data:
        sector = kv_data["sector"]
        if not (1 <= sector <= 1000):
            return False, f"Invalid sector {sector} (must be 1-1000)"

    # Check for credits validity if present
    if "credits" in kv_data:
        credits = kv_data["credits"]
        if credits < 0:
            return False, f"Invalid credits {credits} (must be >= 0)"

    return True, ""


_PORT_CLASS_INLINE_RE = re.compile(r"Class\s*\d+\s*\(([^)]+)\)", re.IGNORECASE)
_PORT_CLASS_NAME_RE = re.compile(r"Class\s*([BS]{3})", re.IGNORECASE)


def is_trade_port_class(port_class: str | None) -> bool:
    """Check if port class is a valid trade port (3-letter B/S code).

    Args:
        port_class: Port class string to validate

    Returns:
        True if valid trade port class
    """
    if not isinstance(port_class, str):
        return False
    if not port_class:
        return False
    return bool(re.fullmatch(r"[BS]{3}", port_class.strip().upper()))


def extract_port_info(bot, screen: str) -> tuple[bool, str | None, str | None]:
    """Extract port information from screen.

    Args:
        bot: TradingBot instance
        screen: Screen text to parse

    Returns:
        Tuple of (has_port, port_class, port_name)
    """
    screen_lower = screen.lower()
    if "no port" in screen_lower:
        return False, None, None

    semantic = extract_semantic_kv(screen)
    has_port = semantic.get("has_port")
    port_class = semantic.get("port_class")
    port_name = semantic.get("port_name")

    if port_class:
        port_class = port_class.strip().upper()
    if port_name:
        port_name = port_name.strip()

    try:
        from bbsbot.games.tw2002.orientation import _parse_sector_display

        sector_info = _parse_sector_display(screen)
    except Exception:
        sector_info = {}

    if sector_info.get("has_port"):
        has_port = True if has_port is None else has_port
        if not port_class:
            port_class = sector_info.get("port_class")

    port_line = None
    for line in screen.splitlines():
        if re.search(r"Ports?\s*:", line, re.IGNORECASE):
            port_line = line
            break

    if not port_class:
        if (class_match := _PORT_CLASS_INLINE_RE.search(screen)) or (class_match := _PORT_CLASS_NAME_RE.search(screen)) or port_line and (class_match := re.search(r"\(([A-Z]{3})\)", port_line)):
            port_class = class_match.group(1).strip().upper()

    if port_name is None and (name_match := re.search(r"Ports?\s*:\s*([^,\n]+)", screen, re.IGNORECASE)):
        port_name = name_match.group(1).strip()

    if has_port is None and port_line:
        has_port = True

    # Fallback to known game state if present
    state = getattr(bot, "game_state", None)
    try:
        from bbsbot.games.tw2002.orientation import GameState as _GameState
    except Exception:
        _GameState = None

    if _GameState is not None and isinstance(state, _GameState):
        if has_port is None:
            has_port = state.has_port
        if not port_class:
            port_class = state.port_class

    return bool(has_port), port_class, port_name


def guard_trade_port(bot, screen: str, context: str) -> None:
    """Validate that we're at a valid trading port.

    Args:
        bot: TradingBot instance
        screen: Current screen text
        context: Context for error message (e.g., "buy", "sell")

    Raises:
        RuntimeError: If port is invalid or special
    """
    has_port, port_class, port_name = extract_port_info(bot, screen)
    screen_lower = screen.lower()

    # Special/unknown port - do not trade.
    # Common special ports: Stardock (Fed HQ), Rylos (Corporate HQ),
    # Hardware (ship/equipment vendor), McPlasma's (weapons vendor)
    special_tokens = ("stardock", "rylos", "special port", "hardware", "mcplasma")
    if port_name and any(token in port_name.lower() for token in special_tokens):
        raise RuntimeError(f"{context}:special_port:{port_name}")
    if any(token in screen_lower for token in special_tokens):
        raise RuntimeError(f"{context}:special_port_screen")

    if not has_port:
        raise RuntimeError(f"{context}:no_port")

    if is_trade_port_class(port_class):
        return

    if port_class:
        raise RuntimeError(f"{context}:special_port_class:{port_class}")
    raise RuntimeError(f"{context}:port_class_unknown")
