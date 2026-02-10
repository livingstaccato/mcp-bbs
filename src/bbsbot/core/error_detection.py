"""Generic error detection and loop checking framework.

This module provides reusable error detection patterns that can be used
across different games and BBS systems.
"""

from __future__ import annotations

from typing import Protocol


class LoopDetector:
    """Generic loop detection for repeated prompts.

    Tracks consecutive occurrences of the same prompt ID to detect
    when the bot is stuck in a loop. Also detects alternating patterns
    (A-B-A-B-A-B) which indicate oscillation between two states.
    """

    def __init__(self, threshold: int = 3):
        """Initialize loop detector.

        Args:
            threshold: Number of consecutive occurrences before considering it a loop
        """
        self.threshold = threshold
        self.last_prompt_id: str | None = None
        self.loop_counts: dict[str, int] = {}

        # Track alternating patterns
        self.alternation_history: list[str] = []
        self.max_history: int = 20

    def check(self, prompt_id: str) -> bool:
        """Check if we're stuck in a loop seeing the same prompt repeatedly.

        Args:
            prompt_id: Current prompt ID

        Returns:
            True if stuck in loop (threshold exceeded), False otherwise
        """
        if prompt_id == self.last_prompt_id:
            self.loop_counts[prompt_id] = self.loop_counts.get(prompt_id, 0) + 1
        else:
            # Different prompt - reset loop detection
            self.loop_counts.clear()
            self.last_prompt_id = prompt_id

        # Track alternating patterns
        self.alternation_history.append(prompt_id)
        if len(self.alternation_history) > self.max_history:
            self.alternation_history = self.alternation_history[-self.max_history :]

        # Detect A-B-A-B-A-B pattern (same 2 prompts alternating)
        if len(self.alternation_history) >= 6:
            recent = self.alternation_history[-6:]
            if len(set(recent)) == 2:  # Only 2 unique prompts
                # Check if alternating: A,B,A,B,A,B
                is_alternating = all(recent[i] != recent[i + 1] for i in range(len(recent) - 1))
                if is_alternating:
                    return True

        count = self.loop_counts.get(prompt_id, 0)
        return count >= self.threshold

    def get_count(self, prompt_id: str) -> int:
        """Get the current loop count for a prompt.

        Args:
            prompt_id: Prompt ID to check

        Returns:
            Number of consecutive occurrences
        """
        return self.loop_counts.get(prompt_id, 0)

    def reset(self) -> None:
        """Reset all loop detection state."""
        self.loop_counts.clear()
        self.last_prompt_id = None
        self.alternation_history.clear()


class ErrorDetector(Protocol):
    """Protocol for game-specific error detection.

    Subclasses should implement detect_error to check for game-specific
    error conditions in screen text.
    """

    def detect_error(self, screen: str) -> str | None:
        """Detect errors in screen text.

        Args:
            screen: Screen text to check for errors

        Returns:
            Error type identifier if detected, None otherwise
        """
        ...


class BaseErrorDetector:
    """Base implementation of ErrorDetector with common patterns.

    Subclasses can extend this to add game-specific error patterns.
    """

    def __init__(self):
        """Initialize base error detector."""
        # Map error patterns to error type identifiers
        self.error_patterns: dict[str, list[str]] = {}

    def add_error_pattern(self, error_type: str, patterns: list[str]) -> None:
        """Register error patterns for a specific error type.

        Args:
            error_type: Identifier for this error type (e.g., "invalid_password")
            patterns: List of lowercase strings to search for in screen text
        """
        self.error_patterns[error_type] = patterns

    def detect_error(self, screen: str) -> str | None:
        """Detect errors in screen text using registered patterns.

        Args:
            screen: Screen text to check for errors

        Returns:
            Error type identifier if detected, None otherwise
        """
        screen_lower = screen.lower()

        for error_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if pattern in screen_lower:
                    return error_type

        return None
