# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for LLM caching and token tracking."""

import time

import pytest

from bbsbot.llm.cache import LLMCache
from bbsbot.llm.types import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    CompletionRequest,
    CompletionResponse,
    TokenUsage,
)
from bbsbot.llm.usage_tracker import UsageTracker


class TestLLMCache:
    """Test LLM response caching."""

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = LLMCache()
        request = ChatRequest(messages=[ChatMessage(role="user", content="Hello")], model="test-model")

        result = cache.get(request)
        assert result is None

    def test_cache_hit(self):
        """Test cache hit returns cached response."""
        cache = LLMCache()
        request = ChatRequest(messages=[ChatMessage(role="user", content="Hello")], model="test-model")
        response = ChatResponse(message=ChatMessage(role="assistant", content="Hi there!"), model="test-model")

        # Store in cache
        cache.set(request, response)

        # Retrieve from cache
        cached = cache.get(request)
        assert cached is not None
        assert cached.message.content == "Hi there!"
        assert cached.cached is True

    def test_cache_key_consistency(self):
        """Test that identical requests produce same cache key."""
        cache = LLMCache()

        request1 = ChatRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            model="test",
            temperature=0.7,
        )
        request2 = ChatRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            model="test",
            temperature=0.7,
        )

        key1 = cache._generate_key(request1)
        key2 = cache._generate_key(request2)

        assert key1 == key2

    def test_cache_different_content(self):
        """Test that different content produces different cache keys."""
        cache = LLMCache()

        request1 = ChatRequest(messages=[ChatMessage(role="user", content="Hello")], model="test")
        request2 = ChatRequest(messages=[ChatMessage(role="user", content="Goodbye")], model="test")

        key1 = cache._generate_key(request1)
        key2 = cache._generate_key(request2)

        assert key1 != key2

    def test_cache_ttl_expiration(self):
        """Test that cache entries expire after TTL."""
        cache = LLMCache(ttl_seconds=1)  # 1 second TTL

        request = ChatRequest(messages=[ChatMessage(role="user", content="Hello")], model="test")
        response = ChatResponse(message=ChatMessage(role="assistant", content="Hi"), model="test")

        cache.set(request, response)

        # Should be cached immediately
        assert cache.get(request) is not None

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        assert cache.get(request) is None

    def test_cache_size_limit(self):
        """Test that cache respects size limits."""
        cache = LLMCache(max_entries=2)

        # Add 3 entries (should evict oldest)
        for i in range(3):
            request = ChatRequest(messages=[ChatMessage(role="user", content=f"Message {i}")], model="test")
            response = ChatResponse(
                message=ChatMessage(role="assistant", content=f"Response {i}"),
                model="test",
            )
            cache.set(request, response)

        # Cache should only have 2 entries
        stats = cache.get_stats()
        assert stats["entries"] == 2

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache = LLMCache()

        request = ChatRequest(messages=[ChatMessage(role="user", content="Hello")], model="test")
        response = ChatResponse(message=ChatMessage(role="assistant", content="Hi"), model="test")

        cache.set(request, response)

        # One miss, one hit
        assert cache.get(ChatRequest(messages=[ChatMessage(role="user", content="Other")], model="test")) is None
        assert cache.get(request) is not None

        stats = cache.get_stats()
        assert stats["total_hits"] == 1
        assert stats["total_misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["entries"] == 1

    def test_completion_request_caching(self):
        """Test that CompletionRequest caching works."""
        cache = LLMCache()

        request = CompletionRequest(prompt="Test prompt", model="test")
        response = CompletionResponse(text="Test response", model="test")

        cache.set(request, response)
        cached = cache.get(request)

        assert cached is not None
        assert cached.text == "Test response"


class TestUsageTracker:
    """Test token usage tracking."""

    def test_track_usage(self):
        """Test basic usage tracking."""
        tracker = UsageTracker()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        tracker.track_usage("test-model", usage)

        stats = tracker.get_all_stats()
        assert stats["total_requests"] == 1
        assert stats["total_tokens"] == 150

    def test_track_cached_usage(self):
        """Test that cached responses are tracked separately."""
        tracker = UsageTracker()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        # Track one normal, one cached
        tracker.track_usage("test-model", usage, cached=False)
        tracker.track_usage("test-model", usage, cached=True)

        stats = tracker.get_all_stats()
        assert stats["total_requests"] == 2
        assert stats["total_cached"] == 1
        assert stats["cache_hit_rate"] == 0.5
        # Cached responses don't add to token count
        assert stats["total_tokens"] == 150

    def test_model_specific_stats(self):
        """Test per-model statistics."""
        tracker = UsageTracker()
        usage1 = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        usage2 = TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300)

        tracker.track_usage("model-1", usage1)
        tracker.track_usage("model-2", usage2)

        stats = tracker.get_all_stats()
        assert len(stats["models"]) == 2
        assert stats["models"]["model-1"]["total_tokens"] == 150
        assert stats["models"]["model-2"]["total_tokens"] == 300

    def test_cost_estimation(self):
        """Test cost estimation."""
        tracker = UsageTracker()
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)

        tracker.track_usage("test-model", usage)

        stats = tracker.get_all_stats()
        # Should have some estimated cost
        assert stats["total_cost_usd"] > 0

    def test_average_calculations(self):
        """Test average token calculations."""
        tracker = UsageTracker()

        # Track 2 requests
        tracker.track_usage("test-model", TokenUsage(100, 50, 150), cached=False)
        tracker.track_usage("test-model", TokenUsage(200, 100, 300), cached=False)

        model_stats = tracker.get_model_stats("test-model")
        assert model_stats is not None
        assert model_stats.avg_prompt_tokens == 150.0  # (100 + 200) / 2
        assert model_stats.avg_completion_tokens == 75.0  # (50 + 100) / 2

    def test_reset_stats(self):
        """Test statistics reset."""
        tracker = UsageTracker()
        usage = TokenUsage(100, 50, 150)

        tracker.track_usage("test-model", usage)
        assert tracker.get_all_stats()["total_requests"] == 1

        tracker.reset()
        assert tracker.get_all_stats()["total_requests"] == 0


class TestTokenUsage:
    """Test TokenUsage type."""

    def test_cost_estimation(self):
        """Test cost estimation property."""
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)

        # Rough estimate: $0.01 per 1K prompt, $0.03 per 1K completion
        expected_cost = (1000 / 1000 * 0.01) + (1000 / 1000 * 0.03)
        assert abs(usage.estimated_cost_usd - expected_cost) < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
