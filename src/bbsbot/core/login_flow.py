"""Generic multi-stage login flow orchestrator.

This module provides a framework for orchestrating multi-stage login sequences.
Games with complex login flows (like TW2002) may implement their own custom logic,
but simpler games can use this framework to reduce boilerplate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class LoginHandler(Protocol):
    """Protocol for game-specific login step handlers.

    Handlers are called when specific prompts are detected during login.
    """

    async def handle_prompt(self, screen: str, prompt_id: str, input_type: str) -> str | None:
        """Handle a login prompt.

        Args:
            screen: Current screen text
            prompt_id: Detected prompt identifier
            input_type: Input type (single_key, multi_key, etc.)

        Returns:
            Response keys to send, or None to skip
        """
        ...


class MultiStageLoginFlow:
    """Generic multi-stage login orchestrator.

    This provides a framework for login flows where you:
    1. Wait for a specific prompt
    2. Send a response
    3. Repeat until logged in

    For complex flows (like TWGS in TW2002), you may prefer to implement
    custom login logic directly.
    """

    def __init__(
        self,
        session: Any,
        wait_for_prompt: Callable,
        send_input: Callable,
    ):
        """Initialize login flow.

        Args:
            session: BBS session object
            wait_for_prompt: Async function to wait for prompts
            send_input: Async function to send input
        """
        self.session = session
        self.wait_for_prompt = wait_for_prompt
        self.send_input = send_input
        self.handlers: dict[str, LoginHandler] = {}

    def register_handler(self, prompt_pattern: str, handler: LoginHandler) -> None:
        """Register a handler for a specific prompt pattern.

        Args:
            prompt_pattern: Pattern to match in prompt_id (e.g., "password")
            handler: Handler to call when this pattern is detected
        """
        self.handlers[prompt_pattern] = handler

    async def execute(
        self,
        target_prompt: str,
        max_steps: int = 20,
        timeout_ms: int = 10000,
    ) -> dict[str, Any]:
        """Execute login flow until target prompt is reached.

        Args:
            target_prompt: Final prompt ID to wait for (e.g., "command_prompt")
            max_steps: Maximum number of steps before giving up
            timeout_ms: Timeout for each step

        Returns:
            Final prompt data with keys: screen, prompt_id, input_type

        Raises:
            RuntimeError: If login fails or max_steps exceeded
        """
        for step in range(max_steps):
            # Wait for next prompt
            result = await self.wait_for_prompt(timeout_ms=timeout_ms)
            prompt_id = result.get("prompt_id", "")
            screen = result.get("screen", "")
            input_type = result.get("input_type", "")

            # Check if we've reached target
            if target_prompt in prompt_id:
                return result

            # Find matching handler
            handler = None
            for pattern, h in self.handlers.items():
                if pattern in prompt_id:
                    handler = h
                    break

            # Call handler if found
            if handler:
                response = await handler.handle_prompt(screen, prompt_id, input_type)
                if response is not None:
                    await self.send_input(response, input_type)
            else:
                # No handler - default to pressing space for any_key prompts
                if input_type == "any_key":
                    await self.send_input("", input_type)

        raise RuntimeError(f"Login failed: max_steps ({max_steps}) exceeded")
