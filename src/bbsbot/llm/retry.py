"""Retry logic with exponential backoff."""

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar

from bbsbot.llm.exceptions import LLMRateLimitError, LLMTimeoutError

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[..., Awaitable[T]],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (
        LLMTimeoutError,
        LLMRateLimitError,
    ),
) -> T:
    """Retry async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_multiplier: Multiplier for each retry delay
        retryable_exceptions: Exceptions that trigger retries

    Returns:
        Result from successful function call

    Raises:
        Last exception if all retries exhausted
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    "llm_retry_attempt",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
                delay *= backoff_multiplier
            else:
                logger.error(
                    "llm_retry_exhausted",
                    max_retries=max_retries,
                    error=str(e),
                )
        except Exception as e:
            # Non-retryable exception - fail immediately
            logger.error("llm_non_retryable_error", error=str(e))
            raise

    # Should never reach here, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic failed unexpectedly")
