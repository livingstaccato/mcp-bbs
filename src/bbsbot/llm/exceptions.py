"""Exception hierarchy for LLM operations."""


class LLMError(Exception):
    """Base exception for LLM operations."""

    pass


class LLMConnectionError(LLMError):
    """Failed to connect to LLM provider."""

    pass


class LLMTimeoutError(LLMError):
    """LLM request timed out."""

    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""

    pass


class LLMModelNotFoundError(LLMError):
    """Requested model not found."""

    pass


class LLMInvalidResponseError(LLMError):
    """Invalid or malformed response from LLM."""

    pass


class LLMAuthenticationError(LLMError):
    """Authentication failed."""

    pass
