"""Generic I/O patterns for BBS interaction.

This module provides reusable I/O patterns with timeout/retry logic
that can be used across different games and BBS systems.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Protocol


class Session(Protocol):
    """Protocol for BBS session objects."""

    async def read(self, timeout_ms: int, max_bytes: int) -> dict[str, Any]:
        """Read from session.

        Returns:
            Dictionary with 'screen' and optionally 'prompt_detected' keys
        """
        ...

    async def send(self, data: str) -> None:
        """Send data to session."""
        ...


class PromptWaiter:
    """Generic wait-for-prompt with timeout/retry logic."""

    def __init__(
        self,
        session: Session,
        on_screen_update: Callable[[str], None] | None = None,
    ):
        """Initialize prompt waiter.

        Args:
            session: BBS session to read from
            on_screen_update: Optional callback for each screen update
        """
        self.session = session
        self.on_screen_update = on_screen_update

    async def wait_for_prompt(
        self,
        expected_prompt_id: str | None = None,
        timeout_ms: int = 10000,
        read_interval_ms: int = 250,
        read_max_bytes: int = 8192,
        on_prompt_detected: Callable[[dict], bool] | None = None,
        require_idle: bool = True,
        idle_grace_ratio: float = 0.8,
    ) -> dict[str, Any]:
        """Wait for prompt detection with optional callback for filtering.

        Args:
            expected_prompt_id: Optional pattern to match (e.g., "prompt.password")
            timeout_ms: Timeout in milliseconds
            read_interval_ms: Interval between reads in milliseconds
            read_max_bytes: Maximum bytes to read per call
            on_prompt_detected: Optional callback called when prompt detected.
                               Should return True to accept the prompt, False to continue waiting.
            require_idle: Whether to wait for screen to stabilize before returning
            idle_grace_ratio: Accept non-idle prompt after this ratio of timeout (0.0-1.0)

        Returns:
            Dictionary with:
                - screen: Screen text
                - prompt_id: Detected prompt ID
                - input_type: Input type (single_key, multi_key, etc.)
                - kv_data: Optional key-value data from prompt
                - is_idle: Whether screen was idle when returned

        Raises:
            TimeoutError: If no matching prompt detected within timeout
        """
        start_time = time.time()
        timeout_sec = timeout_ms / 1000.0
        read_interval_sec = read_interval_ms / 1000.0

        while time.time() - start_time < timeout_sec:
            # Read screen
            snapshot = await self.session.read(
                timeout_ms=read_interval_ms, max_bytes=read_max_bytes
            )
            screen = snapshot.get("screen", "")

            # Call screen update callback if provided
            if self.on_screen_update:
                self.on_screen_update(screen)

            # Check for prompt detection
            if "prompt_detected" in snapshot:
                detected = snapshot["prompt_detected"]
                prompt_id = detected.get("prompt_id")
                is_idle = detected.get("is_idle", False)

                # Wait for screen to stabilize if required
                elapsed = time.time() - start_time
                if require_idle and not is_idle:
                    # Accept non-idle after grace period
                    if elapsed < timeout_sec * idle_grace_ratio:
                        await asyncio.sleep(read_interval_sec)
                        continue

                # Check if prompt matches expected pattern
                if expected_prompt_id:
                    if expected_prompt_id not in prompt_id:
                        await asyncio.sleep(read_interval_sec)
                        continue

                # Call custom filter callback if provided
                if on_prompt_detected:
                    if not on_prompt_detected(detected):
                        await asyncio.sleep(read_interval_sec)
                        continue

                # Return the detected prompt
                return {
                    "screen": screen,
                    "prompt_id": prompt_id,
                    "input_type": detected.get("input_type"),
                    "kv_data": detected.get("kv_data"),
                    "is_idle": is_idle,
                }

            await asyncio.sleep(read_interval_sec)

        raise TimeoutError(f"No prompt detected within {timeout_ms}ms")


class InputSender:
    """Generic input sending with type handling."""

    def __init__(self, session: Session):
        """Initialize input sender.

        Args:
            session: BBS session to send to
        """
        self.session = session

    async def send_input(
        self,
        keys: str,
        input_type: str | None = "multi_key",
        wait_after_sec: float = 0.2,
    ) -> None:
        """Send input respecting prompt type.

        Args:
            keys: The keys/text to send
            input_type: Type of input ("single_key", "multi_key", "any_key")
            wait_after_sec: Time to wait after sending (seconds)
        """
        if input_type == "single_key":
            # Single key - send as-is without newline
            await self.session.send(keys)
        elif input_type == "multi_key":
            # Multi-key - add carriage return
            await self.session.send(keys + "\r")
        elif input_type == "any_key":
            # Any key - press space
            await self.session.send(" ")
        else:
            # Unknown type - default to multi_key (safer)
            await self.session.send(keys + "\r")

        if wait_after_sec > 0:
            await asyncio.sleep(wait_after_sec)
