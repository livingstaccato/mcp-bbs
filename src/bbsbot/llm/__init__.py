# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM provider abstraction layer.

This module provides a unified interface for interacting with different
LLM providers (Ollama, OpenAI, Gemini, etc.) through a protocol-based
architecture.

Public API:
    - LLMProvider: Protocol defining provider interface
    - LLMManager: Provider lifecycle management
    - LLMConfig: Configuration models
    - Request/Response types
    - Exception hierarchy
"""

from bbsbot.llm.base import LLMProvider
from bbsbot.llm.config import GeminiConfig, LLMConfig, OllamaConfig, OpenAIConfig
from bbsbot.llm.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMError,
    LLMInvalidResponseError,
    LLMModelNotFoundError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from bbsbot.llm.manager import LLMManager
from bbsbot.llm.types import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
)

__all__ = [
    # Core
    "LLMProvider",
    "LLMManager",
    # Config
    "LLMConfig",
    "OllamaConfig",
    "OpenAIConfig",
    "GeminiConfig",
    # Types
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "CompletionRequest",
    "CompletionResponse",
    "StreamChunk",
    # Exceptions
    "LLMError",
    "LLMConnectionError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMModelNotFoundError",
    "LLMInvalidResponseError",
    "LLMAuthenticationError",
]
