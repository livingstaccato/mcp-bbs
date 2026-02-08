"""LLM manager for provider lifecycle management."""

from __future__ import annotations

from bbsbot.llm.base import LLMProvider
from bbsbot.llm.cache import LLMCache
from bbsbot.llm.config import LLMConfig
from bbsbot.llm.exceptions import LLMError
from bbsbot.llm.types import ChatRequest, ChatResponse, CompletionRequest, CompletionResponse
from bbsbot.llm.usage_tracker import UsageTracker
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class LLMManager:
    """Manages LLM provider lifecycle.

    Handles provider initialization, response caching, and token usage tracking.

    Features:
    - Automatic response caching with TTL
    - Token usage tracking and cost estimation
    - Cache hit rate monitoring
    - Per-model statistics
    """

    def __init__(
        self,
        config: LLMConfig,
        enable_cache: bool = True,
        cache_ttl: int = 3600,
        max_cache_entries: int = 1000,
    ):
        """Initialize manager.

        Args:
            config: LLM configuration
            enable_cache: Whether to enable response caching (default True)
            cache_ttl: Cache TTL in seconds (default 1 hour)
            max_cache_entries: Maximum cache entries (default 1000)
        """
        self.config = config
        self._provider: LLMProvider | None = None
        self._cache = LLMCache(ttl_seconds=cache_ttl, max_entries=max_cache_entries) if enable_cache else None
        self._usage_tracker = UsageTracker()
        self._enable_cache = enable_cache

    async def get_provider(self) -> LLMProvider:
        """Get or create provider instance.

        Returns:
            LLM provider instance

        Raises:
            LLMError: If provider initialization fails
        """
        if self._provider is None:
            self._provider = await self._create_provider()
        return self._provider

    async def _create_provider(self) -> LLMProvider:
        """Create provider based on configuration.

        Returns:
            Initialized provider instance

        Raises:
            LLMError: If provider type is unsupported or initialization fails
        """
        from bbsbot.llm.providers import get_provider

        try:
            provider = get_provider(self.config)
            logger.info(
                "llm_provider_initialized",
                provider=self.config.provider,
                name=provider.name,
            )
            return provider
        except Exception as e:
            logger.error(
                "llm_provider_init_failed",
                provider=self.config.provider,
                error=str(e),
            )
            raise LLMError(f"Failed to initialize provider: {e}") from e

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Generate chat response with caching and tracking.

        Args:
            request: Chat request

        Returns:
            Chat response (may be cached)
        """
        # Try cache first
        if self._cache:
            cached_response = self._cache.get(request)
            if cached_response:
                logger.debug("llm_cache_hit", model=request.model)
                self._usage_tracker.track_usage(request.model, cached_response.usage, cached=True)
                return cached_response

        # Cache miss - call provider
        provider = await self.get_provider()
        response = await provider.chat(request)

        # Track usage
        self._usage_tracker.track_usage(request.model, response.usage, cached=False)

        # Store in cache
        if self._cache:
            self._cache.set(request, response)

        return response

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate completion with caching and tracking.

        Args:
            request: Completion request

        Returns:
            Completion response (may be cached)
        """
        # Try cache first
        if self._cache:
            cached_response = self._cache.get(request)
            if cached_response:
                logger.debug("llm_cache_hit", model=request.model)
                self._usage_tracker.track_usage(request.model, cached_response.usage, cached=True)
                return cached_response

        # Cache miss - call provider
        provider = await self.get_provider()
        response = await provider.complete(request)

        # Track usage
        self._usage_tracker.track_usage(request.model, response.usage, cached=False)

        # Store in cache
        if self._cache:
            self._cache.set(request, response)

        return response

    async def verify_model(self, model: str) -> dict:
        """Verify a model is available and warm it up.

        For Ollama provider, this checks the model is pulled and loads it
        into memory with keep_alive so subsequent requests are fast.

        Args:
            model: Model name to verify

        Returns:
            Dict with model info

        Raises:
            LLMError: If model is unavailable or provider doesn't support verification
        """
        provider = await self.get_provider()
        if hasattr(provider, "check_model"):
            return await provider.check_model(model)
        # For non-Ollama providers, just verify connectivity
        logger.info("verify_model_skipped", provider=self.config.provider, model=model)
        return {"name": model}

    def get_usage_stats(self) -> dict:
        """Get token usage statistics.

        Returns:
            Dictionary with usage statistics
        """
        return self._usage_tracker.get_all_stats()

    def get_cache_stats(self) -> dict | None:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics or None if caching disabled
        """
        return self._cache.get_stats() if self._cache else None

    def log_usage_summary(self) -> None:
        """Log usage summary to logger."""
        self._usage_tracker.log_summary()

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._usage_tracker.reset()

    def clear_cache(self) -> None:
        """Clear response cache."""
        if self._cache:
            self._cache.clear()
            logger.info("llm_cache_cleared")

    async def close(self) -> None:
        """Cleanup provider resources and log final statistics."""
        # Log final usage summary
        self.log_usage_summary()

        if self._provider:
            await self._provider.close()
            logger.info("llm_provider_closed", provider=self.config.provider)
            self._provider = None
