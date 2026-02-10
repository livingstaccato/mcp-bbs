"""Generic screen parsing utilities for BBS terminals.

This module provides reusable screen parsing functions that can be used
across different games and BBS systems.
"""

import re


def clean_screen_for_display(screen: str, max_lines: int = 30) -> list[str]:
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


def extract_menu_options(screen: str, pattern: str | None = None) -> list[tuple[str, str]]:
    """Extract menu options from screen text.

    Supports common menu formats like:
    - <A> Option Name
    - [A] Option Name
    - (A) Option Name

    Args:
        screen: Screen text containing menu options
        pattern: Optional custom regex pattern. If None, uses default bracket patterns.
                Must have two capture groups: (key, description)

    Returns:
        List of (key, description) tuples, e.g., [('A', 'My Game'), ('B', 'Game 2')]
    """
    if pattern is None:
        # Default pattern for bracket-style menus: <A> or [A] or (A)
        # Handles cases where multiple options are on the same line like "<A> Game1  <B> Game2"
        pattern = r"[<\[\(]([A-Z0-9])[>\]\)]\s+([^<\[\(\n]+?)(?=\s*[<\[\(]|$)"

    options = []
    for match in re.finditer(pattern, screen):
        key = match.group(1)
        description = match.group(2).strip()
        if description:
            options.append((key, description))

    return options


def extract_numbered_list(screen: str, pattern: str | None = None) -> list[tuple[str, str]]:
    """Extract numbered lists from screen text.

    Supports common numbered formats like:
    - 1. Option Name
    - 1) Option Name
    - 1 - Option Name

    Args:
        screen: Screen text containing numbered list
        pattern: Optional custom regex pattern. If None, uses default numbered patterns.
                Must have two capture groups: (number, description)

    Returns:
        List of (number, description) tuples
    """
    if pattern is None:
        # Default pattern for numbered lists
        pattern = r"^\s*(\d+)[\.\)]\s+(.+)$"

    options = []
    for line in screen.splitlines():
        match = re.search(pattern, line)
        if match:
            number = match.group(1)
            description = match.group(2).strip()
            if description:
                options.append((number, description))

    return options


def extract_key_value_pairs(screen: str, patterns: dict[str, str]) -> dict[str, str | int]:
    """Extract key-value pairs from screen text using provided patterns.

    Args:
        screen: Screen text to parse
        patterns: Dictionary mapping field names to regex patterns.
                 Each pattern should have one capture group for the value.

    Returns:
        Dictionary of extracted values (as strings)

    Example:
        patterns = {
            "credits": r"Credits?:?\\s*([\\d,]+)",
            "sector": r"Sector\\s*:?\\s*(\\d+)"
        }
        result = extract_key_value_pairs(screen, patterns)
        # Returns: {"credits": "1,000", "sector": "42"}
    """
    data = {}
    for field, pattern in patterns.items():
        match = re.search(pattern, screen, re.IGNORECASE)
        if match:
            data[field] = match.group(1)
    return data


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from text.

    Args:
        text: Text potentially containing ANSI codes

    Returns:
        Text with ANSI codes removed
    """
    # Pattern matches ANSI escape sequences
    ansi_pattern = r"\x1b\[[0-9;]*[a-zA-Z]"
    return re.sub(ansi_pattern, "", text)
