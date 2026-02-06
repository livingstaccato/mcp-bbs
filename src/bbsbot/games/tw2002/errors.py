"""Error detection and loop checking utilities for TW2002."""

from bbsbot.core.error_detection import BaseErrorDetector, LoopDetector
from bbsbot.games.tw2002.logging_utils import logger


def _check_for_loop(bot, prompt_id: str) -> bool:
    """Check if we're stuck in a loop seeing the same prompt repeatedly.

    Args:
        bot: TradingBot instance
        prompt_id: Current prompt ID

    Returns:
        True if stuck in loop, False otherwise
    """
    # Use the framework LoopDetector
    if not hasattr(bot, "_loop_detector"):
        bot._loop_detector = LoopDetector(threshold=bot.stuck_threshold)

    is_loop = bot._loop_detector.check(prompt_id)
    count = bot._loop_detector.get_count(prompt_id)

    if is_loop:
        logger.warning("loop_detected", prompt_id=prompt_id, count=count, threshold=bot.stuck_threshold)
    elif count > 0:
        logger.debug("loop_detection_tracking", prompt_id=prompt_id, count=count, threshold=bot.stuck_threshold)

    return is_loop


class TW2002ErrorDetector(BaseErrorDetector):
    """TW2002-specific error detection."""

    def __init__(self):
        """Initialize TW2002 error detector with game-specific patterns."""
        super().__init__()

        # Register TW2002-specific error patterns
        self.add_error_pattern("invalid_password", ["invalid password"])
        self.add_error_pattern("insufficient_credits", ["not enough credits", "insufficient funds"])
        self.add_error_pattern("hold_full", ["hold full", "cargo hold is full"])
        self.add_error_pattern("ship_destroyed", ["you are dead", "destroyed"])
        self.add_error_pattern("out_of_turns", ["out of turns", "no turns remaining"])


def _detect_error_in_screen(screen: str) -> str | None:
    """Detect common error messages in screen text.

    Args:
        screen: Screen text to check

    Returns:
        Error type if detected, None otherwise
    """
    detector = TW2002ErrorDetector()
    return detector.detect_error(screen)
