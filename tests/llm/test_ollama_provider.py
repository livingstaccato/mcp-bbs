"""Tests for Ollama provider."""

from unittest.mock import MagicMock, patch

import pytest

from bbsbot.llm.config import OllamaConfig
from bbsbot.llm.exceptions import (
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMTimeoutError,
)
from bbsbot.llm.providers.ollama import OllamaProvider
from bbsbot.llm.types import ChatMessage, ChatRequest, CompletionRequest


@pytest.fixture
def ollama_config():
    """Create test Ollama config."""
    return OllamaConfig(
        base_url="http://localhost:11434",
        model="llama2",
        timeout_seconds=10.0,
        max_retries=1,
    )


@pytest.fixture
async def ollama_provider(ollama_config):
    """Create Ollama provider for testing."""
    provider = OllamaProvider(ollama_config)
    yield provider
    await provider.close()


@pytest.mark.asyncio
async def test_ollama_completion_success(ollama_provider):
    """Test successful completion request."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "response": "Hello, world!",
        "done": True,
        "done_reason": "stop",
    }

    with patch.object(ollama_provider._client, "post", return_value=mock_response) as mock_post:
        request = CompletionRequest(
            prompt="Hello",
            model="llama2",
        )
        response = await ollama_provider.complete(request)

        assert response.text == "Hello, world!"
        assert response.model == "llama2"
        assert response.finish_reason == "stop"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_ollama_chat_success(ollama_provider):
    """Test successful chat request."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "Hello!"},
        "done": True,
        "done_reason": "stop",
    }

    with patch.object(ollama_provider._client, "post", return_value=mock_response) as mock_post:
        request = ChatRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            model="llama2",
        )
        response = await ollama_provider.chat(request)

        assert response.message.role == "assistant"
        assert response.message.content == "Hello!"
        assert response.finish_reason == "stop"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_ollama_connection_error(ollama_provider):
    """Test connection error handling."""
    import httpx

    with patch.object(
        ollama_provider._client,
        "post",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        request = CompletionRequest(prompt="Hello", model="llama2")

        with pytest.raises(LLMConnectionError):
            await ollama_provider.complete(request)


@pytest.mark.asyncio
async def test_ollama_timeout_error(ollama_provider):
    """Test timeout error handling."""
    import httpx

    with patch.object(
        ollama_provider._client,
        "post",
        side_effect=httpx.TimeoutException("Request timeout"),
    ):
        request = CompletionRequest(prompt="Hello", model="llama2")

        with pytest.raises(LLMTimeoutError):
            await ollama_provider.complete(request)


@pytest.mark.asyncio
async def test_ollama_model_not_found(ollama_provider):
    """Test model not found error."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch.object(
        ollama_provider._client,
        "post",
        side_effect=httpx.HTTPStatusError("Model not found", request=MagicMock(), response=mock_response),
    ):
        request = CompletionRequest(prompt="Hello", model="nonexistent")

        with pytest.raises(LLMModelNotFoundError):
            await ollama_provider.complete(request)


@pytest.mark.asyncio
async def test_ollama_health_check_success(ollama_provider):
    """Test health check success."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch.object(ollama_provider._client, "get", return_value=mock_response):
        result = await ollama_provider.health_check()
        assert result is True


@pytest.mark.asyncio
async def test_ollama_health_check_failure(ollama_provider):
    """Test health check failure."""
    import httpx

    with patch.object(
        ollama_provider._client,
        "get",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        result = await ollama_provider.health_check()
        assert result is False
