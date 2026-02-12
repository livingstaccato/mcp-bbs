# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Screen analysis and verification tool for TW2002 prompt detection.

This module provides diagnostic tools to verify that game screens are properly
matched by prompt detection rules and handled correctly by the bot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.bot import TradingBot

logger = get_logger(__name__)


class ScreenAnalysis(BaseModel):
    """Analysis of a game screen and its prompt detection."""

    screen_text: str
    screen_hash: str
    prompt_id: str | None
    input_type: str | None
    kv_data: dict[str, Any]
    matched_pattern: str | None
    cursor_at_end: bool
    has_trailing_space: bool
    all_patterns_checked: list[str]
    patterns_partially_matched: list[dict[str, Any]]
    recommendation: str


async def analyze_screen(bot: TradingBot) -> ScreenAnalysis:
    """Analyze current screen and show detection details.

    This function provides comprehensive diagnostics about:
    - What the bot sees on screen
    - Which prompt rule matched (if any)
    - What data was extracted
    - Why other patterns didn't match
    - What the bot should do next

    Args:
        bot: TradingBot instance with active session

    Returns:
        ScreenAnalysis with full diagnostic information
    """
    # Get current screen snapshot
    snapshot = bot.session.emulator.get_snapshot()
    screen_text = snapshot.get("screen", "")
    screen_hash = snapshot.get("screen_hash", "")
    cursor_at_end = snapshot.get("cursor_at_end", True)
    has_trailing_space = snapshot.get("has_trailing_space", False)

    # Run prompt detection to see what matched
    detection = None
    if bot.session.learning and bot.session.learning._prompt_detector:
        detection = bot.session.learning._prompt_detector.detect_prompt(snapshot)

    # Extract results
    prompt_id = detection.prompt_id if detection else None
    input_type = detection.input_type if detection else None
    matched_pattern = detection.pattern.get("regex") if detection else None
    kv_extract = detection.kv_extract if detection else None

    # Extract K/V data if available
    kv_data = {}
    if kv_extract:
        from bbsbot.learning.extractor import extract_kv

        kv_data = extract_kv(screen_text, kv_extract)

    # Get list of all patterns that were checked
    all_patterns = []
    if bot.session.learning and bot.session.learning._prompt_detector:
        all_patterns = [p.get("id", "unknown") for _, p in bot.session.learning._prompt_detector._compiled]

    # Generate recommendation
    recommendation = _generate_recommendation(
        screen_text=screen_text,
        prompt_id=prompt_id,
        input_type=input_type,
        cursor_at_end=cursor_at_end,
    )

    return ScreenAnalysis(
        screen_text=screen_text,
        screen_hash=screen_hash,
        prompt_id=prompt_id,
        input_type=input_type,
        kv_data=kv_data,
        matched_pattern=matched_pattern,
        cursor_at_end=cursor_at_end,
        has_trailing_space=has_trailing_space,
        all_patterns_checked=all_patterns,
        patterns_partially_matched=[],  # TODO: Track this in detector
        recommendation=recommendation,
    )


def _generate_recommendation(
    screen_text: str,
    prompt_id: str | None,
    input_type: str | None,
    cursor_at_end: bool,
) -> str:
    """Generate recommendation for what the bot should do next.

    Args:
        screen_text: Current screen content
        prompt_id: Matched prompt ID (if any)
        input_type: Matched input type (if any)
        cursor_at_end: Whether cursor is at end of screen

    Returns:
        Human-readable recommendation
    """
    if not prompt_id:
        if not cursor_at_end:
            return (
                "NO MATCH: Cursor not at end - likely data display, not a prompt. "
                "Bot should wait or try pressing Space/Enter to advance."
            )
        if not screen_text.strip():
            return (
                "NO MATCH: Blank screen - connection issue or server processing. "
                "Bot should wait or send wake-up key (Space/NUL)."
            )
        return (
            f"NO MATCH: No prompt pattern matched. "
            f"This may be an unknown screen that needs a new rule in rules.json. "
            f"Screen content: {screen_text[-200:]!r}"
        )

    # Matched - provide context-specific guidance
    if "sector_command" in prompt_id:
        return (
            "MATCHED: Bot is at sector command prompt. Should execute next strategy action (warp, dock, display, etc.)"
        )
    elif "port" in prompt_id.lower():
        return "MATCHED: Bot is at port. Should execute trade based on strategy."
    elif "pause" in prompt_id.lower():
        return "MATCHED: Pause screen detected. Bot should press Space or Enter to continue."
    elif "menu" in prompt_id.lower():
        return "MATCHED: Menu detected. Bot should select game letter or press Q to exit."
    elif "password" in prompt_id.lower() or "login" in prompt_id.lower():
        return "MATCHED: Login/password prompt. Bot should enter credentials."
    else:
        return f"MATCHED: {prompt_id} (input_type: {input_type}). Bot should respond based on prompt type."


def format_screen_analysis(analysis: ScreenAnalysis) -> str:
    """Format screen analysis for display in terminal or dashboard.

    Args:
        analysis: ScreenAnalysis to format

    Returns:
        Formatted multi-line string
    """
    lines = [
        "=" * 80,
        "SCREEN ANALYSIS",
        "=" * 80,
        "",
        "Screen Content:",
        "-" * 80,
        analysis.screen_text,
        "-" * 80,
        "",
        f"Screen Hash: {analysis.screen_hash}",
        f"Cursor at End: {analysis.cursor_at_end}",
        f"Has Trailing Space: {analysis.has_trailing_space}",
        "",
        "Prompt Detection:",
        f"  Matched Prompt: {analysis.prompt_id or 'NONE'}",
        f"  Input Type: {analysis.input_type or 'N/A'}",
        f"  Pattern: {analysis.matched_pattern or 'N/A'}",
        "",
        "Extracted Data:",
    ]

    if analysis.kv_data:
        for key, value in sorted(analysis.kv_data.items()):
            lines.append(f"  {key}: {value}")
    else:
        lines.append("  (none)")

    lines.extend(
        [
            "",
            "Recommendation:",
            f"  {analysis.recommendation}",
            "",
            f"Total Patterns Checked: {len(analysis.all_patterns_checked)}",
            "=" * 80,
        ]
    )

    return "\n".join(lines)
