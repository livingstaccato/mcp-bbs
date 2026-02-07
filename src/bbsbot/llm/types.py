"""Type definitions for LLM requests and responses."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TokenUsage:
    """Token usage statistics for an LLM request/response."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    @property
    def estimated_cost_usd(self) -> float:
        """Estimate cost in USD based on typical pricing.

        This is a rough estimate - actual costs vary by provider and model.
        Assumes ~$0.01 per 1K prompt tokens, ~$0.03 per 1K completion tokens.
        """
        prompt_cost = (self.prompt_tokens / 1000) * 0.01
        completion_cost = (self.completion_tokens / 1000) * 0.03
        return prompt_cost + completion_cost


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class CompletionRequest:
    """Request for text completion."""

    prompt: str
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    stop: list[str] | None = None


@dataclass
class CompletionResponse:
    """Response from text completion."""

    text: str
    model: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None  # Token usage statistics
    cached: bool = False  # Whether this response was served from cache


@dataclass
class ChatRequest:
    """Request for chat completion."""

    messages: list[ChatMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    stop: list[str] | None = None


@dataclass
class ChatResponse:
    """Response from chat completion."""

    message: ChatMessage
    model: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None  # Token usage statistics
    cached: bool = False  # Whether this response was served from cache


@dataclass
class StreamChunk:
    """Streaming response chunk."""

    delta: str
    finish_reason: str | None = None
