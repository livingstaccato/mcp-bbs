"""Gemini provider implementation (stub)."""

from collections.abc import AsyncIterator

from bbsbot.llm.config import GeminiConfig
from bbsbot.llm.types import (
    ChatRequest,
    ChatResponse,
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
)


class GeminiProvider:
    """Gemini LLM provider (not yet implemented).

    This is a placeholder for future Gemini integration.
    """

    name = "gemini"

    def __init__(self, config: GeminiConfig):
        """Initialize Gemini provider.

        Args:
            config: Gemini configuration
        """
        self.config = config

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate text completion.

        Raises:
            NotImplementedError: Gemini provider not yet implemented
        """
        raise NotImplementedError("Gemini provider not yet implemented")

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Generate chat response.

        Raises:
            NotImplementedError: Gemini provider not yet implemented
        """
        raise NotImplementedError("Gemini provider not yet implemented")

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream chat response.

        Raises:
            NotImplementedError: Gemini provider not yet implemented
        """
        raise NotImplementedError("Gemini provider not yet implemented")
        # Make this a proper async generator
        if False:
            yield

    async def health_check(self) -> bool:
        """Check if Gemini is available.

        Returns:
            False (not implemented)
        """
        return False

    async def close(self) -> None:
        """Cleanup resources."""
        pass
