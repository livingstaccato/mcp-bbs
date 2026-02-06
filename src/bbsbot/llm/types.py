"""Type definitions for LLM requests and responses."""

from dataclasses import dataclass, field
from typing import Literal


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


@dataclass
class StreamChunk:
    """Streaming response chunk."""

    delta: str
    finish_reason: str | None = None
