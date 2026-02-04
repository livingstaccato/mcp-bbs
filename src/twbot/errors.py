"""Error detection and loop checking utilities."""

from typing import Optional

from .logging_utils import logger


def _check_for_loop(bot, prompt_id: str) -> bool:
    """Check if we're stuck in a loop seeing the same prompt repeatedly.

    Args:
        bot: TradingBot instance
        prompt_id: Current prompt ID

    Returns:
        True if stuck in loop, False otherwise
    """
    # Track how many times we've seen this prompt consecutively
    if prompt_id == bot.last_prompt_id:
        bot.loop_detection[prompt_id] = bot.loop_detection.get(prompt_id, 0) + 1
    else:
        # Different prompt - reset loop detection
        bot.loop_detection.clear()
        bot.last_prompt_id = prompt_id

    count = bot.loop_detection.get(prompt_id, 0)
    if count >= bot.stuck_threshold:
        print(f"  ⚠️  LOOP DETECTED: {prompt_id} seen {count} times")
        return True

    return False


def _detect_error_in_screen(screen: str) -> Optional[str]:
    """Detect common error messages in screen text.

    Args:
        screen: Screen text to check

    Returns:
        Error type if detected, None otherwise
    """
    screen_lower = screen.lower()

    if "invalid password" in screen_lower:
        return "invalid_password"
    elif "not enough credits" in screen_lower or "insufficient funds" in screen_lower:
        return "insufficient_credits"
    elif "hold full" in screen_lower or "cargo hold is full" in screen_lower:
        return "hold_full"
    elif "you are dead" in screen_lower or "destroyed" in screen_lower:
        return "ship_destroyed"
    elif "out of turns" in screen_lower or "no turns remaining" in screen_lower:
        return "out_of_turns"

    return None
