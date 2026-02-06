"""Token usage tracking and cost estimation for LLM calls."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from bbsbot.llm.types import TokenUsage

logger = logging.getLogger(__name__)


@dataclass
class ModelUsageStats:
    """Usage statistics for a specific model."""

    model: str
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    cached_responses: int = 0
    estimated_cost_usd: float = 0.0

    def add_usage(self, usage: TokenUsage, cached: bool = False) -> None:
        """Add a usage record to statistics.

        Args:
            usage: Token usage from an LLM call
            cached: Whether this was a cached response
        """
        self.total_requests += 1
        if not cached:
            self.total_prompt_tokens += usage.prompt_tokens
            self.total_completion_tokens += usage.completion_tokens
            self.total_tokens += usage.total_tokens
            self.estimated_cost_usd += usage.estimated_cost_usd
        else:
            self.cached_responses += 1

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        if self.total_requests == 0:
            return 0.0
        return self.cached_responses / self.total_requests

    @property
    def avg_prompt_tokens(self) -> float:
        """Calculate average prompt tokens per request."""
        non_cached = self.total_requests - self.cached_responses
        if non_cached == 0:
            return 0.0
        return self.total_prompt_tokens / non_cached

    @property
    def avg_completion_tokens(self) -> float:
        """Calculate average completion tokens per request."""
        non_cached = self.total_requests - self.cached_responses
        if non_cached == 0:
            return 0.0
        return self.total_completion_tokens / non_cached


class UsageTracker:
    """Track LLM token usage across all models and requests.

    Features:
    - Per-model usage tracking
    - Cost estimation
    - Cache hit rate monitoring
    - Session-level statistics
    """

    def __init__(self):
        """Initialize usage tracker."""
        self._model_stats: dict[str, ModelUsageStats] = defaultdict(
            lambda: ModelUsageStats(model="unknown")
        )
        self._session_start = None
        self._total_requests = 0
        self._total_cached = 0

    def track_usage(
        self, model: str, usage: TokenUsage | None, cached: bool = False
    ) -> None:
        """Track usage for an LLM call.

        Args:
            model: Model name/identifier
            usage: Token usage information (None if not available)
            cached: Whether this was a cached response
        """
        self._total_requests += 1
        if cached:
            self._total_cached += 1

        if usage is None:
            return

        stats = self._model_stats[model]
        if stats.model == "unknown":
            stats.model = model

        stats.add_usage(usage, cached)

        # Log significant usage
        if usage.total_tokens > 10000:
            logger.warning(
                "large_llm_request",
                model=model,
                tokens=usage.total_tokens,
                cost_usd=usage.estimated_cost_usd,
            )

    def get_model_stats(self, model: str) -> ModelUsageStats | None:
        """Get statistics for a specific model.

        Args:
            model: Model name

        Returns:
            Usage statistics or None if model not found
        """
        return self._model_stats.get(model)

    def get_all_stats(self) -> dict[str, Any]:
        """Get all usage statistics.

        Returns:
            Dictionary with comprehensive usage statistics
        """
        total_tokens = sum(s.total_tokens for s in self._model_stats.values())
        total_cost = sum(s.estimated_cost_usd for s in self._model_stats.values())
        cache_hit_rate = (
            self._total_cached / self._total_requests if self._total_requests > 0 else 0.0
        )

        return {
            "total_requests": self._total_requests,
            "total_cached": self._total_cached,
            "cache_hit_rate": cache_hit_rate,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "models": {
                model: {
                    "requests": stats.total_requests,
                    "prompt_tokens": stats.total_prompt_tokens,
                    "completion_tokens": stats.total_completion_tokens,
                    "total_tokens": stats.total_tokens,
                    "cached_responses": stats.cached_responses,
                    "cache_hit_rate": stats.cache_hit_rate,
                    "avg_prompt_tokens": stats.avg_prompt_tokens,
                    "avg_completion_tokens": stats.avg_completion_tokens,
                    "estimated_cost_usd": stats.estimated_cost_usd,
                }
                for model, stats in self._model_stats.items()
            },
        }

    def reset(self) -> None:
        """Reset all statistics."""
        self._model_stats.clear()
        self._total_requests = 0
        self._total_cached = 0

    def log_summary(self) -> None:
        """Log a summary of usage statistics."""
        stats = self.get_all_stats()

        logger.info(
            "llm_usage_summary",
            total_requests=stats["total_requests"],
            total_tokens=stats["total_tokens"],
            cache_hit_rate=f"{stats['cache_hit_rate']:.1%}",
            estimated_cost=f"${stats['total_cost_usd']:.4f}",
        )

        for model, model_stats in stats["models"].items():
            logger.info(
                "llm_model_stats",
                model=model,
                requests=model_stats["requests"],
                tokens=model_stats["total_tokens"],
                cost=f"${model_stats['estimated_cost_usd']:.4f}",
            )
