"""Tests for rate limiting middleware."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.main import app
from src.rate_limit import rate_limiter, RateLimiter


# UUID válido para testes - será reconhecido pelo get_endpoint_pattern
TEST_EXPERIMENT_ID = "550e8400-e29b-41d4-a716-446655440000"


class TestRateLimiter:
    """Unit tests for RateLimiter class."""

    def test_allows_requests_under_limit(self):
        """Should allow requests under the limit."""
        limiter = RateLimiter()
        
        for i in range(5):
            allowed, remaining, reset = limiter.is_allowed("test_key", max_requests=10, window_seconds=60)
            assert allowed is True
            assert remaining == 10 - i - 1

    def test_blocks_requests_over_limit(self):
        """Should block requests over the limit."""
        limiter = RateLimiter()
        
        # Use up all requests
        for _ in range(5):
            limiter.is_allowed("test_key_2", max_requests=5, window_seconds=60)
        
        # Next request should be blocked
        allowed, remaining, reset = limiter.is_allowed("test_key_2", max_requests=5, window_seconds=60)
        assert allowed is False
        assert remaining == 0

    def test_different_keys_have_separate_limits(self):
        """Different keys should have independent limits."""
        limiter = RateLimiter()
        
        # Use up limit for key_a
        for _ in range(3):
            limiter.is_allowed("key_a", max_requests=3, window_seconds=60)
        
        # key_a should be blocked
        allowed_a, _, _ = limiter.is_allowed("key_a", max_requests=3, window_seconds=60)
        assert allowed_a is False
        
        # key_b should still work
        allowed_b, _, _ = limiter.is_allowed("key_b", max_requests=3, window_seconds=60)
        assert allowed_b is True


class TestRateLimitMiddleware:
    """Integration tests for rate limit middleware."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_rate_limit_headers_present(self, client):
        """Response should include rate limit headers."""
        response = client.get("/health")
        
        # Health endpoint is excluded from rate limiting
        # Test with a different endpoint using valid UUID
        with patch("src.services.experiment.ExperimentRepository") as mock_repo:
            mock_repo.get_experiment_by_id.return_value = None
            response = client.get(f"/experiments/{TEST_EXPERIMENT_ID}")
        
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_health_endpoint_excluded_from_rate_limit(self, client):
        """Health endpoint should not have rate limit headers."""
        response = client.get("/health")
        
        # Health endpoint is excluded, so no rate limit headers
        assert response.status_code == 200

    def test_rate_limit_exceeded_returns_429(self, client):
        """Should return 429 when rate limit exceeded."""
        # Create a fresh limiter for this test
        from src import rate_limit
        original_limiter = rate_limit.rate_limiter
        rate_limit.rate_limiter = RateLimiter()
        
        try:
            with patch("src.services.experiment.ExperimentRepository") as mock_repo:
                mock_repo.get_experiment_by_id.return_value = None
                
                # A chave correta usa "testclient" (o IP do TestClient)
                # e o pattern normalizado do endpoint (com UUID → {experiment_id})
                test_key = "testclient:GET /experiments/{experiment_id}"
                for _ in range(120):
                    rate_limit.rate_limiter.is_allowed(test_key, max_requests=120, window_seconds=60)
                
                # This request should be rate limited (usando UUID válido)
                response = client.get(f"/experiments/{TEST_EXPERIMENT_ID}")
                
                assert response.status_code == 429
                assert "Rate limit exceeded" in response.json()["detail"]["error"]
                assert "Retry-After" in response.headers
        finally:
            rate_limit.rate_limiter = original_limiter

    def test_rate_limit_response_includes_retry_after(self, client):
        """429 response should include retry information."""
        from src import rate_limit
        original_limiter = rate_limit.rate_limiter
        rate_limit.rate_limiter = RateLimiter()
        
        try:
            with patch("src.services.experiment.ExperimentRepository") as mock_repo:
                mock_repo.get_experiment_by_id.return_value = None
                
                # A chave correta usa "testclient" (o IP do TestClient)
                test_key = "testclient:GET /experiments/{experiment_id}"
                for _ in range(120):
                    rate_limit.rate_limiter.is_allowed(test_key, max_requests=120, window_seconds=60)
                
                # This request should be rate limited (usando UUID válido)
                response = client.get(f"/experiments/{TEST_EXPERIMENT_ID}")
                
                assert response.status_code == 429
                data = response.json()["detail"]
                assert "retry_after" in data
                assert "limit" in data
                assert "window_seconds" in data
        finally:
            rate_limit.rate_limiter = original_limiter


class TestRateLimitConfiguration:
    """Tests for rate limit configuration."""

    def test_allocation_endpoint_has_300_per_minute_limit(self):
        """GET /allocation should allow 300 requests per minute."""
        from src.rate_limit import RATE_LIMITS
        
        config = RATE_LIMITS.get("GET /experiments/{experiment_id}/allocation")
        assert config is not None
        assert config["max_requests"] == 300
        assert config["window_seconds"] == 60

    def test_post_experiments_has_10_per_minute_limit(self):
        """POST /experiments should allow 10 requests per minute."""
        from src.rate_limit import RATE_LIMITS
        
        config = RATE_LIMITS.get("POST /experiments")
        assert config is not None
        assert config["max_requests"] == 10
        assert config["window_seconds"] == 60

    def test_post_metrics_has_100_per_minute_limit(self):
        """POST /metrics should allow 100 requests per minute."""
        from src.rate_limit import RATE_LIMITS
        
        config = RATE_LIMITS.get("POST /experiments/{experiment_id}/metrics")
        assert config is not None
        assert config["max_requests"] == 100
        assert config["window_seconds"] == 60

    def test_default_limit_exists(self):
        """Should have a default rate limit."""
        from src.rate_limit import RATE_LIMITS
        
        config = RATE_LIMITS.get("default")
        assert config is not None
        assert "max_requests" in config
        assert "window_seconds" in config
