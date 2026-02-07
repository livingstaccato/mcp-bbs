"""Ollama provider implementation."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from bbsbot.llm.config import OllamaConfig
from bbsbot.llm.exceptions import (
    LLMConnectionError,
    LLMInvalidResponseError,
    LLMModelNotFoundError,
    LLMTimeoutError,
)
from bbsbot.llm.retry import retry_with_backoff
from bbsbot.llm.types import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
)

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Ollama LLM provider implementation.

    Provides access to local Ollama models via HTTP API.
    """

    name = "ollama"

    def __init__(self, config: OllamaConfig):
        """Initialize Ollama provider.

        Args:
            config: Ollama configuration
        """
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
        )

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate text completion.

        Args:
            request: Completion request

        Returns:
            Completion response

        Raises:
            LLMError: On API errors
        """

        async def _make_request() -> CompletionResponse:
            payload = {
                "model": request.model,
                "prompt": request.prompt,
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                },
            }
            if request.max_tokens:
                payload["options"]["num_predict"] = request.max_tokens
            if request.stop:
                payload["options"]["stop"] = request.stop

            try:
                response = await self._client.post("/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()

                return CompletionResponse(
                    text=data.get("response", ""),
                    model=request.model,
                    finish_reason=data.get("done_reason"),
                )
            except httpx.ConnectError as e:
                raise LLMConnectionError(
                    f"Failed to connect to Ollama at {self.config.base_url}"
                ) from e
            except httpx.TimeoutException as e:
                raise LLMTimeoutError(
                    f"Request timed out after {self.config.timeout_seconds}s"
                ) from e
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise LLMModelNotFoundError(
                        f"Model '{request.model}' not found"
                    ) from e
                raise LLMInvalidResponseError(f"HTTP {e.response.status_code}") from e

        return await retry_with_backoff(
            _make_request,
            max_retries=self.config.max_retries,
            initial_delay=self.config.retry_delay_seconds,
            backoff_multiplier=self.config.retry_backoff_multiplier,
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Generate chat response.

        Args:
            request: Chat request

        Returns:
            Chat response

        Raises:
            LLMError: On API errors
        """

        async def _make_request() -> ChatResponse:
            # Convert messages to Ollama format
            messages = [
                {"role": msg.role, "content": msg.content} for msg in request.messages
            ]

            payload: dict[str, Any] = {
                "model": request.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                },
            }
            if request.max_tokens:
                payload["options"]["num_predict"] = request.max_tokens
            if request.stop:
                payload["options"]["stop"] = request.stop

            try:
                response = await self._client.post("/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()

                message_data = data.get("message", {})
                return ChatResponse(
                    message=ChatMessage(
                        role="assistant",
                        content=message_data.get("content", ""),
                    ),
                    model=request.model,
                    finish_reason=data.get("done_reason"),
                )
            except httpx.ConnectError as e:
                raise LLMConnectionError(
                    f"Failed to connect to Ollama at {self.config.base_url}"
                ) from e
            except httpx.TimeoutException as e:
                raise LLMTimeoutError(
                    f"Request timed out after {self.config.timeout_seconds}s"
                ) from e
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise LLMModelNotFoundError(
                        f"Model '{request.model}' not found"
                    ) from e
                raise LLMInvalidResponseError(f"HTTP {e.response.status_code}") from e

        return await retry_with_backoff(
            _make_request,
            max_retries=self.config.max_retries,
            initial_delay=self.config.retry_delay_seconds,
            backoff_multiplier=self.config.retry_backoff_multiplier,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream chat response.

        Args:
            request: Chat request

        Yields:
            Stream chunks

        Raises:
            LLMError: On API errors
        """
        messages = [
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ]

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
            },
        }
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens
        if request.stop:
            payload["options"]["stop"] = request.stop

        try:
            async with self._client.stream(
                "POST", "/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            message_data = data.get("message", {})
                            delta = message_data.get("content", "")
                            done = data.get("done", False)

                            yield StreamChunk(
                                delta=delta,
                                finish_reason=data.get("done_reason") if done else None,
                            )
                        except json.JSONDecodeError:
                            logger.warning("ollama_invalid_stream_chunk", line=line)
                            continue
        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f"Failed to connect to Ollama at {self.config.base_url}"
            ) from e
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(
                f"Request timed out after {self.config.timeout_seconds}s"
            ) from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise LLMModelNotFoundError(f"Model '{request.model}' not found") from e
            raise LLMInvalidResponseError(f"HTTP {e.response.status_code}") from e

    async def health_check(self) -> bool:
        """Check if Ollama is available.

        Returns:
            True if Ollama is responding
        """
        try:
            response = await self._client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning("ollama_health_check_failed", error=str(e))
            return False

    async def close(self) -> None:
        """Cleanup HTTP client."""
        await self._client.aclose()
