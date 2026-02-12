# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Base protocol for LLM providers."""

from collections.abc import AsyncIterator
from typing import Protocol

from bbsbot.llm.types import (
    ChatRequest,
    ChatResponse,
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
)


class LLMProvider(Protocol):
    """Protocol for LLM provider implementations.

    This defines the interface that all LLM providers must implement.
    Providers can be swapped out without changing consumer code.
    """

    name: str

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate text completion.

        Args:
            request: Completion request parameters

        Returns:
            Completion response with generated text

        Raises:
            LLMError: On provider-specific errors
        """
        ...

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Generate chat response.

        Args:
            request: Chat request with message history

        Returns:
            Chat response with assistant message

        Raises:
            LLMError: On provider-specific errors
        """
        ...

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream chat response.

        Args:
            request: Chat request with message history

        Yields:
            Stream chunks as they arrive

        Raises:
            LLMError: On provider-specific errors
        """
        ...

    async def health_check(self) -> bool:
        """Check if provider is available.

        Returns:
            True if provider is healthy and accessible
        """
        ...

    async def close(self) -> None:
        """Cleanup resources.

        Called when provider is no longer needed.
        """
        ...
