# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Generic I/O patterns for BBS interaction.

This module provides reusable I/O patterns with timeout/retry logic
that can be used across different games and BBS systems.
"""

from __future__ import annotations

import asyncio
import time
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable


class Session(Protocol):
    """Protocol for BBS session objects."""

    async def wait_for_update(self, *, timeout_ms: int, since: int | None = None) -> bool:
        """Wait until new bytes arrive from the remote (or until timeout)."""
        ...

    def snapshot(self) -> dict[str, Any]:
        """Return latest snapshot without performing network I/O."""
        ...

    async def send(self, data: str) -> None:
        """Send data to session."""
        ...


async def session_is_connected(session: Any) -> bool:
    """Return connection state for sync or async `is_connected` implementations."""
    checker = getattr(session, "is_connected", None)
    if checker is None:
        return True
    value = checker() if callable(checker) else checker
    if isawaitable(value):
        value = await value
    return bool(value)


class PromptWaiter:
    """Generic wait-for-prompt with timeout/retry logic."""

    def __init__(
        self,
        session: Session | None,
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
        on_prompt_detected: Callable[[dict], bool] | None = None,
        on_prompt_seen: Callable[[dict], None] | None = None,
        on_prompt_rejected: Callable[[dict, str], None] | None = None,
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
            on_prompt_seen: Optional callback fired when any prompt candidate is seen.
            on_prompt_rejected: Optional callback fired when a candidate is rejected.
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
        start_mono = time.monotonic()
        timeout_sec = timeout_ms / 1000.0
        read_interval_sec = read_interval_ms / 1000.0  # used only as a backstop timer

        while time.monotonic() - start_mono < timeout_sec:
            if self.session is None:
                # The owning bot disconnected and cleared its session reference.
                # Treat as a recoverable network failure so the worker can reconnect.
                raise ConnectionError("Session is None")
            if not await session_is_connected(self.session):
                raise ConnectionError("Session disconnected")

            snapshot = self.session.snapshot()
            screen = snapshot.get("screen", "")

            # Call screen update callback if provided
            if self.on_screen_update:
                self.on_screen_update(screen)

            # Check for prompt detection
            if "prompt_detected" in snapshot:
                detected = snapshot["prompt_detected"]
                # Enrich prompt metadata with the current screen for downstream logic
                # (e.g. password error detection, loop diagnostics).
                detected_full = dict(detected or {})
                detected_full["screen"] = screen
                detected_full["screen_hash"] = snapshot.get("screen_hash", "")
                detected_full["captured_at"] = snapshot.get("captured_at")
                prompt_id = str(detected.get("prompt_id") or "")
                is_idle = detected.get("is_idle", False)
                if on_prompt_seen:
                    on_prompt_seen(detected_full)

                # Wait for screen to stabilize if required
                elapsed = time.monotonic() - start_mono
                if require_idle and not is_idle and elapsed < timeout_sec * idle_grace_ratio:
                    if on_prompt_rejected:
                        on_prompt_rejected(detected_full, "not_idle")
                    # Wait until either: new bytes arrive (screen still changing), or idle timer elapses.
                    remaining_idle = getattr(self.session, "seconds_until_idle", lambda _t=2.0: read_interval_sec)()
                    wait_ms = int(max(1, min(remaining_idle, timeout_sec - elapsed) * 1000))
                    await self.session.wait_for_update(timeout_ms=wait_ms)
                    continue

                # Check if prompt matches expected pattern
                if expected_prompt_id and expected_prompt_id not in prompt_id:
                    if on_prompt_rejected:
                        on_prompt_rejected(detected_full, "expected_mismatch")
                    await self.session.wait_for_update(timeout_ms=int(read_interval_sec * 1000))
                    continue

                # Call custom filter callback if provided
                if on_prompt_detected and not on_prompt_detected(detected_full):
                    if on_prompt_rejected:
                        on_prompt_rejected(detected_full, "callback_reject")
                    await self.session.wait_for_update(timeout_ms=int(read_interval_sec * 1000))
                    continue

                # Return the detected prompt
                return {
                    "screen": screen,
                    "prompt_id": prompt_id,
                    "input_type": detected.get("input_type"),
                    "kv_data": detected_full.get("kv_data"),
                    "is_idle": is_idle,
                }

            # No prompt yet; block until the next network update or timeout window.
            remaining = timeout_sec - (time.monotonic() - start_mono)
            if remaining <= 0:
                break
            await self.session.wait_for_update(timeout_ms=int(min(read_interval_sec, remaining) * 1000))

        raise TimeoutError(f"No prompt detected within {timeout_ms}ms")


class InputSender:
    """Generic input sending with type handling."""

    def __init__(self, session: Session | None):
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
        if self.session is None:
            raise ConnectionError("Session is None")
        if not await session_is_connected(self.session):
            raise ConnectionError("Session disconnected")

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
