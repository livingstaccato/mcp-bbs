"""LLM manager for provider lifecycle management."""

import logging

from bbsbot.llm.base import LLMProvider
from bbsbot.llm.config import LLMConfig
from bbsbot.llm.exceptions import LLMError

logger = logging.getLogger(__name__)


class LLMManager:
    """Manages LLM provider lifecycle.

    Handles provider initialization, caching, and cleanup.
    """

    def __init__(self, config: LLMConfig):
        """Initialize manager.

        Args:
            config: LLM configuration
        """
        self.config = config
        self._provider: LLMProvider | None = None

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

    async def close(self) -> None:
        """Cleanup provider resources."""
        if self._provider:
            await self._provider.close()
            logger.info("llm_provider_closed", provider=self.config.provider)
            self._provider = None
