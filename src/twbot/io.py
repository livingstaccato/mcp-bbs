"""Core I/O operations for TW2002 Trading Bot."""

import asyncio
import time
from typing import Optional

from .errors import _detect_error_in_screen, _check_for_loop


async def wait_and_respond(
    bot,
    prompt_id_pattern: Optional[str] = None,
    timeout_ms: int = 10000,
) -> tuple[Optional[str], Optional[str], str]:
    """Wait for prompt and return (input_type, prompt_id, screen).

    Args:
        bot: TradingBot instance
        prompt_id_pattern: Optional pattern to match (e.g., "prompt.password")
        timeout_ms: Timeout in milliseconds

    Returns:
        Tuple of (input_type, prompt_id, screen_text)

    Raises:
        TimeoutError: If no prompt detected within timeout
        RuntimeError: If error detected in screen or stuck in loop
    """
    bot.step_count += 1
    start_time = time.time()
    timeout_sec = timeout_ms / 1000.0

    while time.time() - start_time < timeout_sec:
        # Use session.read() which runs prompt detection
        snapshot = await bot.session.read(timeout_ms=250, max_bytes=8192)
        screen = snapshot.get("screen", "")

        if "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            prompt_id = detected.get("prompt_id")
            input_type = detected.get("input_type")

            # Only check for context-specific errors (not menu-wide error text)
            # Check for errors ONLY if we're at a password/login prompt
            if prompt_id and any(
                x in prompt_id
                for x in [
                    "password",
                    "game_password",
                    "private_game_password",
                    "login_name",
                ]
            ):
                error_type = _detect_error_in_screen(screen)
                if error_type:
                    bot.error_count += 1
                    raise RuntimeError(f"Error detected: {error_type}")

            # Check for loop
            if _check_for_loop(bot, prompt_id):
                raise RuntimeError(f"Stuck in loop: {prompt_id}")

            # If pattern specified, check if it matches
            if prompt_id_pattern:
                if prompt_id_pattern in prompt_id:
                    bot.detected_prompts.append(
                        {
                            "step": bot.step_count,
                            "prompt_id": prompt_id,
                            "input_type": input_type,
                        }
                    )
                    return (input_type, prompt_id, screen)
            else:
                # Any prompt is acceptable
                bot.detected_prompts.append(
                    {
                        "step": bot.step_count,
                        "prompt_id": prompt_id,
                        "input_type": input_type,
                    }
                )
                return (input_type, prompt_id, screen)

        await asyncio.sleep(0.1)

    raise TimeoutError(f"No prompt detected within {timeout_ms}ms")


async def send_input(
    bot, keys: str, input_type: Optional[str], wait_after: float = 0.2
):
    """Send input based on input_type metadata.

    Args:
        bot: TradingBot instance
        keys: The keys/text to send
        input_type: Type from prompt metadata ("single_key", "multi_key", "any_key")
        wait_after: Time to wait after sending (seconds)
    """
    if input_type == "single_key":
        # Single key - send as-is without newline
        await bot.session.send(keys)
    elif input_type == "multi_key":
        # Multi-key - add newline
        await bot.session.send(keys + "\r")
    elif input_type == "any_key":
        # Any key - press space
        await bot.session.send(" ")
    else:
        # Unknown type - default to multi_key (safer)
        await bot.session.send(keys + "\r")

    await asyncio.sleep(wait_after)
