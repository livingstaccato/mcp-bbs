# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for LLM configuration."""

import pytest

from bbsbot.llm.config import LLMConfig, OllamaConfig, OpenAIConfig


def test_ollama_config_defaults():
    """Test Ollama config defaults."""
    config = OllamaConfig()

    assert config.base_url == "http://localhost:11434"
    assert config.model == "gemma3"
    assert config.timeout_seconds == 30.0
    assert config.max_retries == 3


def test_llm_config_defaults():
    """Test LLM config defaults."""
    config = LLMConfig()

    assert config.provider == "ollama"
    assert config.ollama is not None
    assert config.openai is None
    assert config.gemini is None
    assert config.get_model() == "gemma3"


def test_llm_config_with_custom_ollama():
    """Test LLM config with custom Ollama settings."""
    config = LLMConfig(
        provider="ollama",
        ollama=OllamaConfig(
            base_url="http://custom:8080",
            model="llama3",
            timeout_seconds=60.0,
        ),
    )

    assert config.provider == "ollama"
    assert config.ollama.base_url == "http://custom:8080"
    assert config.ollama.model == "llama3"
    assert config.ollama.timeout_seconds == 60.0
    assert config.get_model() == "llama3"


def test_llm_config_openai():
    """Test LLM config with OpenAI."""
    config = LLMConfig(
        provider="openai",
        openai=OpenAIConfig(
            api_key="sk-test",
            model="gpt-4",
        ),
    )

    assert config.provider == "openai"
    assert config.openai is not None
    assert config.openai.api_key == "sk-test"
    assert config.openai.model == "gpt-4"
    assert config.get_model() == "gpt-4"


def test_llm_config_openai_missing_nested_config_raises():
    config = LLMConfig(provider="openai", openai=None)
    with pytest.raises(ValueError, match="llm\\.openai is not configured"):
        config.get_model()
