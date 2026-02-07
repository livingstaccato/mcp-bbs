"""Error detection and loop checking utilities for TW2002."""

import asyncio

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


def _check_for_error_loop(bot, screen: str) -> bool:
    """Check if we're stuck in a loop seeing the same error repeatedly.

    Args:
        bot: TradingBot instance
        screen: Current screen text

    Returns:
        True if stuck in error loop, False otherwise
    """
    # Track recent errors
    if not hasattr(bot, "_error_history"):
        bot._error_history = []

    # Detect error in current screen
    error_type = _detect_error_in_screen(screen)

    if error_type:
        # Add to history (keep last 10)
        bot._error_history.append(error_type)
        bot._error_history = bot._error_history[-10:]

        # Check if same error repeated 3+ times in a row
        if len(bot._error_history) >= 3:
            recent_errors = bot._error_history[-3:]
            if all(e == error_type for e in recent_errors):
                logger.warning("error_loop_detected", error_type=error_type, count=3)
                return True

    return False


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
        self.add_error_pattern("not_in_corporation", ["not on a corp", "not in a corporation", "sorry, you're not"])
        self.add_error_pattern("invalid_command", ["invalid choice", "invalid command", "huh?", "what?"])


def _detect_error_in_screen(screen: str) -> str | None:
    """Detect common error messages in screen text.

    Args:
        screen: Screen text to check

    Returns:
        Error type if detected, None otherwise
    """
    detector = TW2002ErrorDetector()
    return detector.detect_error(screen)


async def escape_loop(bot) -> bool:
    """Escape from a stuck loop by sending quit commands.

    Tries multiple escape sequences:
    1. Q (quit)
    2. ESC
    3. X (exit)
    4. Multiple Q presses

    Args:
        bot: TradingBot instance

    Returns:
        True if escape successful, False otherwise
    """
    logger.warning("attempting_loop_escape")

    # Clear loop detection state
    if hasattr(bot, "_loop_detector"):
        bot._loop_detector.clear()
    if hasattr(bot, "_error_history"):
        bot._error_history = []

    # Try escape sequences
    escape_sequences = [
        ("Q", "Sending Q to quit"),
        ("\x1b", "Sending ESC"),
        ("X", "Sending X to exit"),
        ("Q\rQ\r", "Sending multiple Q"),
    ]

    for sequence, description in escape_sequences:
        logger.debug("loop_escape_attempt", action=description)
        await bot.session.send(sequence)
        await asyncio.sleep(0.5)

        # Check if we're at a different state
        result = await bot.session.read(timeout_ms=1000, max_bytes=8192)
        screen = result.get("screen", "")

        # If we see command prompt or sector prompt, we escaped
        if "command" in screen.lower() and "[" in screen:
            logger.info("loop_escape_successful", method=description)
            return True

    logger.error("loop_escape_failed")
    return False
