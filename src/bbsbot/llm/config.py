"""Configuration models for LLM providers."""

from typing import Literal

from pydantic import BaseModel, Field


class OllamaConfig(BaseModel):
    """Configuration for Ollama provider."""

    base_url: str = "http://localhost:11434"
    model: str = "llama2"
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

    def get_model(self) -> str:
        """Return the configured model name for the active provider.

        Today we primarily use Ollama. For other providers, raise a clear error
        if their nested config isn't set to avoid silently using the wrong model.
        """
        if self.provider == "ollama":
            return self.ollama.model
        if self.provider == "openai":
            if not self.openai:
                raise ValueError("LLM provider is openai but llm.openai is not configured")
            return self.openai.model
        if self.provider == "gemini":
            if not self.gemini:
                raise ValueError("LLM provider is gemini but llm.gemini is not configured")
            return self.gemini.model
        # Defensive: Literal should prevent this, but keep a stable error.
        raise ValueError(f"Unknown LLM provider: {self.provider}")
