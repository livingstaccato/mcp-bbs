"""Prompt detection with cursor-aware pattern matching."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from bbsbot.learning.buffer import ScreenBuffer
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class PromptMatch(BaseModel):
    """Represents a matched prompt pattern."""

    prompt_id: str
    pattern: dict[str, Any]
    input_type: str  # "single_key" | "multi_key" | "any_key"
    eol_pattern: str
    kv_extract: list[dict[str, Any]] | dict[str, Any] | None = None


class PromptDetection(BaseModel):
    """Complete prompt detection result with context."""

    prompt_id: str
    input_type: str
    is_idle: bool
    buffer: ScreenBuffer
    kv_data: dict[str, Any] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PromptDetector:
    """Intelligent prompt detection with cursor-awareness."""

    def __init__(self, patterns: list[dict[str, Any]]) -> None:
        """Initialize prompt detector.

        Args:
            patterns: List of prompt pattern dictionaries from JSON
        """
        self._patterns = patterns
        self._compiled = self._compile_patterns()

    def _compile_patterns(self) -> list[tuple[re.Pattern[str], dict[str, Any]]]:
        """Compile regex patterns for efficient matching.

        Returns:
            List of (compiled_regex, pattern_dict) tuples
        """
        compiled = []
        failed_patterns = []

        logger.info(f"[PATTERN COMPILE] Compiling {len(self._patterns)} patterns")

        for pattern in self._patterns:
            try:
                regex = re.compile(pattern["regex"], re.MULTILINE)
                compiled.append((regex, pattern))
                logger.debug(f"[PATTERN COMPILE] ✓ Compiled: {pattern.get('id', 'unknown')}")
            except re.error as e:
                # Pattern compilation failed - emit diagnostic
                failed_patterns.append({
                    "id": pattern.get("id", "unknown"),
                    "regex": pattern.get("regex", ""),
                    "error": str(e),
                })
                logger.error(
                    f"[PATTERN COMPILE] ✗ FAILED to compile pattern: {pattern.get('id', 'unknown')}\n"
                    f"  Regex: {pattern.get('regex', '')!r}\n"
                    f"  Error: {e}"
                )
                continue
            except KeyError as e:
                # Pattern missing required 'regex' key
                logger.error(
                    f"[PATTERN COMPILE] ✗ INVALID pattern structure (missing key): {pattern.get('id', 'unknown')}\n"
                    f"  Missing key: {e}\n"
                    f"  Pattern keys: {list(pattern.keys())}"
                )
                failed_patterns.append({
                    "id": pattern.get("id", "unknown"),
                    "error": f"Missing key: {e}",
                })
                continue

        logger.info(
            f"[PATTERN COMPILE] Compilation complete: {len(compiled)} succeeded, "
            f"{len(failed_patterns)} failed"
        )

        if failed_patterns:
            logger.error(
                f"[PATTERN COMPILE] ⚠️  {len(failed_patterns)} patterns failed compilation:\n" +
                "\n".join(f"  - {p['id']}: {p.get('error', 'unknown error')}" for p in failed_patterns)
            )

        return compiled

    def detect_prompt(self, snapshot: dict[str, Any]) -> PromptMatch | None:
        """Detect if snapshot contains a prompt waiting for input.

        Args:
            snapshot: Screen snapshot with timing and cursor metadata

        Returns:
            PromptMatch if a prompt pattern matches, None otherwise
        """
        screen = snapshot["screen"]
        # Most callers supply cursor metadata; tests/legacy callers may not.
        # Defaulting to True keeps prompt detection working for minimal snapshots.
        cursor_at_end = snapshot.get("cursor_at_end", True)
        has_trailing_space = snapshot.get("has_trailing_space", False)

        # Track patterns that partially matched (for diagnostics)
        regex_matched_but_failed: list[dict[str, Any]] = []

        logger.debug(f"[PROMPT DETECTION] Checking {len(self._compiled)} patterns")
        logger.debug(f"[PROMPT DETECTION] Cursor at end: {cursor_at_end}, Has trailing space: {has_trailing_space}")
        logger.debug(f"[PROMPT DETECTION] Screen content ({len(screen)} chars):\n{screen[-200:]}")  # Last 200 chars

        for regex, pattern in self._compiled:
            match = regex.search(screen)
            if not match:
                continue

            # Regex matched! Now check additional constraints
            logger.debug(f"[PROMPT DETECTION] ✓ Regex MATCHED: {pattern['id']}")
            logger.debug(f"[PROMPT DETECTION]   Pattern: {regex.pattern}")
            logger.debug(f"[PROMPT DETECTION]   Matched text: {match.group()!r}")

            negative = pattern.get("negative_regex")
            if negative and re.search(negative, screen, re.MULTILINE | re.IGNORECASE):
                logger.warning(
                    f"[PROMPT DETECTION] ✗ REJECTED by negative_match: {pattern['id']}\n"
                    f"  Negative pattern: {negative}\n"
                    f"  Pattern would have matched but negative check excludes it"
                )
                regex_matched_but_failed.append({
                    "pattern_id": pattern["id"],
                    "reason": "negative_match",
                    "negative_pattern": negative,
                })
                continue

            # Check if cursor position matches expectations
            expect_cursor_at_end = pattern.get("expect_cursor_at_end", True)
            if expect_cursor_at_end and not cursor_at_end:
                # Likely data display, not a prompt waiting for input
                logger.warning(
                    f"[PROMPT DETECTION] ✗ REJECTED by cursor position: {pattern['id']}\n"
                    f"  Expected cursor at end: {expect_cursor_at_end}\n"
                    f"  Actual cursor at end: {cursor_at_end}\n"
                    f"  Pattern matched but cursor position doesn't indicate a prompt"
                )
                regex_matched_but_failed.append({
                    "pattern_id": pattern["id"],
                    "reason": "cursor_position",
                    "expected_cursor_at_end": expect_cursor_at_end,
                    "actual_cursor_at_end": cursor_at_end,
                })
                continue

            # Matched!
            logger.info(f"[PROMPT DETECTION] ✓✓✓ MATCHED: {pattern['id']} (input_type: {pattern.get('input_type', 'multi_key')})")
            return PromptMatch(
                prompt_id=pattern["id"],
                pattern=pattern,
                input_type=pattern.get("input_type", "multi_key"),
                eol_pattern=pattern.get("eol_pattern", r"[\r\n]+"),
                kv_extract=pattern.get("kv_extract"),
            )

        # NO PATTERNS MATCHED - Emit diagnostic
        if regex_matched_but_failed:
            logger.error(
                f"[PROMPT DETECTION] ✗✗✗ DETECTION FAILED: {len(regex_matched_but_failed)} patterns matched "
                f"regex but failed additional checks:\n" +
                "\n".join(f"  - {p['pattern_id']}: {p['reason']}" for p in regex_matched_but_failed)
            )
        else:
            # No patterns matched at all - this might be okay (e.g., data display)
            logger.debug(
                f"[PROMPT DETECTION] No patterns matched screen content\n"
                f"  Total patterns: {len(self._compiled)}\n"
                f"  Screen preview: {screen[-150:]!r}"
            )

        return None

    def auto_detect_input_type(self, screen: str) -> str:
        """Heuristically detect input type from prompt text.

        Args:
            screen: Screen text to analyze

        Returns:
            "any_key", "single_key", or "multi_key"
        """
        screen_lower = screen.lower()

        # "Press any key" type prompts
        if any(
            phrase in screen_lower
            for phrase in [
                "press any key",
                "press a key",
                "hit any key",
                "strike any key",
                "<more>",
                "[more]",
                "-- more --",
            ]
        ):
            return "any_key"

        # Single key choice prompts (Y/N, menu selections)
        if any(
            phrase in screen_lower
            for phrase in [
                "(y/n)",
                "(yes/no)",
                "continue?",
                "quit?",
                "abort?",
                "retry?",
                "[y/n]",
                "(q)uit",
                "(a)bort",
            ]
        ):
            return "single_key"

        # Multi-key field input prompts
        if any(
            phrase in screen_lower
            for phrase in [
                "enter",
                "type",
                "input",
                "name:",
                "password:",
                "username:",
                "choose:",
                "select:",
                "command:",
                "search:",
            ]
        ):
            return "multi_key"

        # Default to multi_key (safest, waits for EOL)
        return "multi_key"

    def add_pattern(self, pattern: dict[str, Any]) -> None:
        """Add a new pattern to the detector.

        Args:
            pattern: Pattern dictionary to add
        """
        self._patterns.append(pattern)
        # Recompile patterns
        self._compiled = self._compile_patterns()

    def reload_patterns(self, patterns: list[dict[str, Any]]) -> None:
        """Replace all patterns with new set.

        Args:
            patterns: New list of pattern dictionaries
        """
        self._patterns = patterns
        self._compiled = self._compile_patterns()
