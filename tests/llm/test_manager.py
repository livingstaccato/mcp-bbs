"""Tests for LLM manager."""

import pytest

from bbsbot.llm.config import LLMConfig, OllamaConfig
from bbsbot.llm.manager import LLMManager


@pytest.fixture
def llm_config():
    """Create test LLM config."""
    return LLMConfig(
        provider="ollama",
        ollama=OllamaConfig(
            base_url="http://localhost:11434",
            model="llama2",
        ),
    )


@pytest.mark.asyncio
async def test_manager_get_provider(llm_config):
    """Test getting provider from manager."""
    manager = LLMManager(llm_config)

    provider = await manager.get_provider()
    assert provider is not None
    assert provider.name == "ollama"

    # Should return same instance
    provider2 = await manager.get_provider()
    assert provider2 is provider

    await manager.close()


@pytest.mark.asyncio
async def test_manager_close(llm_config):
    """Test closing manager."""
    manager = LLMManager(llm_config)
    await manager.get_provider()

    await manager.close()

    # After close, should create new provider
    provider = await manager.get_provider()
    assert provider is not None
