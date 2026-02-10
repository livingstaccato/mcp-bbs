"""LLM response caching with TTL support."""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from bbsbot.llm.types import ChatRequest, ChatResponse, CompletionRequest, CompletionResponse


@dataclass
class CacheEntry:
    """Cached LLM response with metadata."""

    response: ChatResponse | CompletionResponse
    created_at: float
    hits: int = 0
    last_accessed: float = 0.0


class LLMCache:
    """In-memory cache for LLM responses with TTL.

    Features:
    - Content-based hashing for cache keys
    - TTL (time-to-live) for automatic expiration
    - Hit tracking for statistics
    - Size limits to prevent unbounded growth
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 1000):
        """Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
            max_entries: Maximum number of entries to keep (default 1000)
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._cache: dict[str, CacheEntry] = {}
        self._total_hits = 0
        self._total_misses = 0

    def _generate_key(self, request: ChatRequest | CompletionRequest) -> str:
        """Generate cache key from request.

        Uses content-based hashing to ensure identical requests
        produce the same cache key regardless of request order.

        Args:
            request: LLM request to hash

        Returns:
            Hex digest of request content
        """
        # Convert request to dict and sort keys for consistent hashing
        req_dict = asdict(request)

        # Normalize messages for ChatRequest
        if hasattr(request, "messages"):
            # Sort messages by role then content for consistency
            messages = req_dict.get("messages", [])
            req_dict["messages"] = sorted(messages, key=lambda m: (m["role"], m["content"]))

        # Create deterministic JSON string
        req_json = json.dumps(req_dict, sort_keys=True)

        # Hash the JSON
        return hashlib.sha256(req_json.encode()).hexdigest()

    def get(self, request: ChatRequest | CompletionRequest) -> ChatResponse | CompletionResponse | None:
        """Get cached response if available and not expired.

        Args:
            request: LLM request to look up

        Returns:
            Cached response if available, None otherwise
        """
        key = self._generate_key(request)
        entry = self._cache.get(key)

        if entry is None:
            self._total_misses += 1
            return None

        # Check if entry has expired
        age = time.time() - entry.created_at
        if age > self.ttl_seconds:
            # Entry expired, remove it
            del self._cache[key]
            self._total_misses += 1
            return None

        # Update hit statistics
        entry.hits += 1
        entry.last_accessed = time.time()
        self._total_hits += 1

        # Mark response as cached
        response = entry.response
        response.cached = True

        return response

    def set(
        self,
        request: ChatRequest | CompletionRequest,
        response: ChatResponse | CompletionResponse,
    ) -> None:
        """Store response in cache.

        Args:
            request: LLM request
            response: LLM response to cache
        """
        # Check size limit
        if len(self._cache) >= self.max_entries:
            self._evict_oldest()

        key = self._generate_key(request)
        entry = CacheEntry(response=response, created_at=time.time(), last_accessed=time.time())
        self._cache[key] = entry

    def _evict_oldest(self) -> None:
        """Evict least recently used entry."""
        if not self._cache:
            return

        # Find entry with oldest last_accessed time
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
        del self._cache[oldest_key]

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._total_hits + self._total_misses
        hit_rate = self._total_hits / total_requests if total_requests > 0 else 0.0

        return {
            "entries": len(self._cache),
            "max_entries": self.max_entries,
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
            "hit_rate": hit_rate,
            "ttl_seconds": self.ttl_seconds,
        }

    def prune_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries pruned
        """
        now = time.time()
        expired_keys = [key for key, entry in self._cache.items() if (now - entry.created_at) > self.ttl_seconds]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)
