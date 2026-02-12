# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider registry and factory."""

from bbsbot.llm.base import LLMProvider
from bbsbot.llm.config import LLMConfig
from bbsbot.llm.exceptions import LLMError


def get_provider(config: LLMConfig) -> LLMProvider:
    """Get provider instance based on configuration.

    Args:
        config: LLM configuration

    Returns:
        Initialized provider instance

    Raises:
        LLMError: If provider type is unsupported
    """
    if config.provider == "ollama":
        from bbsbot.llm.providers.ollama import OllamaProvider

        return OllamaProvider(config.ollama)

    elif config.provider == "openai":
        from bbsbot.llm.providers.openai import OpenAIProvider

        if config.openai is None:
            raise LLMError("OpenAI config required but not provided")
        return OpenAIProvider(config.openai)

    elif config.provider == "gemini":
        from bbsbot.llm.providers.gemini import GeminiProvider

        if config.gemini is None:
            raise LLMError("Gemini config required but not provided")
        return GeminiProvider(config.gemini)

    else:
        raise LLMError(f"Unsupported provider: {config.provider}")


__all__ = ["get_provider"]
