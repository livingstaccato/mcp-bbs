"""Prompt detection with cursor-aware pattern matching."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from bbsbot.learning.buffer import ScreenBuffer


class PromptMatch(BaseModel):
    """Represents a matched prompt pattern."""

    prompt_id: str
    pattern: dict[str, Any]
    input_type: str  # "single_key" | "multi_key" | "any_key"
    eol_pattern: str
    kv_extract: dict[str, Any] | None = None


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
        for pattern in self._patterns:
            try:
                regex = re.compile(pattern["regex"], re.MULTILINE)
                compiled.append((regex, pattern))
            except re.error:
                # Skip invalid patterns
                continue
        return compiled

    def detect_prompt(self, snapshot: dict[str, Any]) -> PromptMatch | None:
        """Detect if snapshot contains a prompt waiting for input.

        Args:
            snapshot: Screen snapshot with timing and cursor metadata

        Returns:
            PromptMatch if a prompt pattern matches, None otherwise
        """
        screen = snapshot["screen"]
        cursor_at_end = snapshot.get("cursor_at_end", False)
        has_trailing_space = snapshot.get("has_trailing_space", False)

        for regex, pattern in self._compiled:
            if not regex.search(screen):
                continue
            negative = pattern.get("negative_regex")
            if negative and re.search(negative, screen, re.MULTILINE | re.IGNORECASE):
                continue

            # Check if cursor position matches expectations
            expect_cursor_at_end = pattern.get("expect_cursor_at_end", True)
            if expect_cursor_at_end and not cursor_at_end:
                # Likely data display, not a prompt waiting for input
                continue

            # Matched!
            return PromptMatch(
                prompt_id=pattern["id"],
                pattern=pattern,
                input_type=pattern.get("input_type", "multi_key"),
                eol_pattern=pattern.get("eol_pattern", r"[\r\n]+"),
                kv_extract=pattern.get("kv_extract"),
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
