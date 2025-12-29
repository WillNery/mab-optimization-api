"""Tests for request logging middleware."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware import RequestLoggingMiddleware


class TestRequestLoggingMiddleware:
    """Tests for RequestLoggingMiddleware."""

    @pytest.fixture
    def app_with_middleware(self):
        """Create a test app with the middleware."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        
        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}
        
        @app.get("/health")
        async def health_endpoint():
            return {"status": "healthy"}
        
        @app.get("/error")
        async def error_endpoint():
            raise ValueError("Test error")
        
        return app

    @pytest.fixture
    def client(self, app_with_middleware):
        """Create test client."""
        return TestClient(app_with_middleware, raise_server_exceptions=False)

    def test_logs_successful_request(self, client):
        """Should log successful requests."""
        with patch("src.middleware.log_request") as mock_log:
            response = client.get("/test")
            
            assert response.status_code == 200
            mock_log.assert_called_once()
            
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["method"] == "GET"
            assert call_kwargs["path"] == "/test"
            assert call_kwargs["status_code"] == 200
            assert "duration_ms" in call_kwargs

    def test_skips_health_endpoint(self, client):
        """Should not log health check requests."""
        with patch("src.middleware.log_request") as mock_log:
            response = client.get("/health")
            
            assert response.status_code == 200
            mock_log.assert_not_called()

    def test_logs_client_ip_from_header(self, client):
        """Should extract client IP from X-Forwarded-For header."""
        with patch("src.middleware.log_request") as mock_log:
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "203.0.113.195, 70.41.3.18"}
            )
            
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["client_ip"] == "203.0.113.195"

    def test_logs_request_id_if_provided(self, client):
        """Should include X-Request-ID in logs if provided."""
        with patch("src.middleware.log_request") as mock_log:
            response = client.get(
                "/test",
                headers={"X-Request-ID": "req-12345"}
            )
            
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["request_id"] == "req-12345"

    def test_returns_request_id_in_response(self, client):
        """Should return X-Request-ID in response headers."""
        with patch("src.middleware.log_request"):
            response = client.get(
                "/test",
                headers={"X-Request-ID": "req-12345"}
            )
            
            assert response.headers.get("X-Request-ID") == "req-12345"

    def test_logs_user_agent(self, client):
        """Should log user agent."""
        with patch("src.middleware.log_request") as mock_log:
            response = client.get(
                "/test",
                headers={"User-Agent": "TestClient/1.0"}
            )
            
            call_kwargs = mock_log.call_args[1]
            assert "TestClient" in call_kwargs["user_agent"]

    def test_truncates_long_user_agent(self, client):
        """Should truncate very long user agents."""
        with patch("src.middleware.log_request") as mock_log:
            long_ua = "A" * 200
            response = client.get(
                "/test",
                headers={"User-Agent": long_ua}
            )
            
            call_kwargs = mock_log.call_args[1]
            assert len(call_kwargs["user_agent"]) <= 100

    def test_logs_query_params(self, client):
        """Should log query parameters."""
        with patch("src.middleware.log_request") as mock_log:
            response = client.get("/test?foo=bar&baz=123")
            
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["query_params"] is not None
            assert "foo=bar" in call_kwargs["query_params"]

    def test_logs_errors(self, client):
        """Should log errors with log_error."""
        with patch("src.middleware.log_error") as mock_log_error:
            with patch("src.middleware.log_request"):
                response = client.get("/error")
                
                # The middleware should catch and log the error
                mock_log_error.assert_called_once()
                call_kwargs = mock_log_error.call_args[1]
                assert call_kwargs["error_type"] == "ValueError"

    def test_measures_duration(self, client):
        """Should measure request duration."""
        with patch("src.middleware.log_request") as mock_log:
            response = client.get("/test")
            
            call_kwargs = mock_log.call_args[1]
            assert "duration_ms" in call_kwargs
            assert isinstance(call_kwargs["duration_ms"], float)
            assert call_kwargs["duration_ms"] >= 0
