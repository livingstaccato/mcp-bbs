"""Configuration models for LLM providers."""

from typing import Literal

from pydantic import BaseModel, Field


class OllamaConfig(BaseModel):
    """Configuration for Ollama provider."""

    base_url: str = "http://localhost:11434"
    model: str = "gemma3"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    retry_backoff_multiplier: float = 2.0


class OpenAIConfig(BaseModel):
    """Configuration for OpenAI provider."""

    api_key: str | None = None
    model: str = "gpt-4"
    timeout_seconds: float = 30.0
    max_retries: int = 3


class GeminiConfig(BaseModel):
    """Configuration for Gemini provider."""

    api_key: str | None = None
    model: str = "gemini-pro"
    timeout_seconds: float = 30.0
    max_retries: int = 3


class LLMConfig(BaseModel):
    """Main LLM configuration."""

    provider: Literal["ollama", "openai", "gemini"] = "ollama"
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openai: OpenAIConfig | None = None
    gemini: GeminiConfig | None = None
