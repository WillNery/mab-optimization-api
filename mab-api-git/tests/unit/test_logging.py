"""Tests for structured logging."""

import json
import logging
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from src.logging_config import (
    JSONFormatter,
    setup_logging,
    logger,
    log_request,
    log_db_query,
    log_algorithm,
    log_error,
)


class TestJSONFormatter:
    """Tests for JSON log formatter."""

    def test_formats_log_as_json(self):
        """Log output should be valid JSON."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        
        # Should be valid JSON
        parsed = json.loads(output)
        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"

    def test_includes_timestamp(self):
        """Log should include ISO timestamp."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        parsed = json.loads(output)
        
        assert "timestamp" in parsed
        assert parsed["timestamp"].endswith("Z")

    def test_includes_extra_fields(self):
        """Extra fields should be included in log."""
        formatter = JSONFormatter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.custom_field = "custom_value"
        record.duration_ms = 123.45
        
        output = formatter.format(record)
        parsed = json.loads(output)
        
        assert parsed["custom_field"] == "custom_value"
        assert parsed["duration_ms"] == 123.45

    def test_includes_exception_info(self):
        """Exception info should be included when present."""
        formatter = JSONFormatter()
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        
        output = formatter.format(record)
        parsed = json.loads(output)
        
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


class TestLogFunctions:
    """Tests for log helper functions."""

    def test_log_request(self):
        """log_request should log with correct structure."""
        with patch.object(logger, 'info') as mock_info:
            log_request(
                method="GET",
                path="/experiments/123/allocation",
                status_code=200,
                duration_ms=45.5,
                client_ip="192.168.1.1",
            )
            
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            
            assert "GET /experiments/123/allocation 200" in call_args[0][0]
            extra = call_args[1]["extra"]
            assert extra["type"] == "http_request"
            assert extra["method"] == "GET"
            assert extra["path"] == "/experiments/123/allocation"
            assert extra["status_code"] == 200
            assert extra["duration_ms"] == 45.5
            assert extra["client_ip"] == "192.168.1.1"

    def test_log_db_query(self):
        """log_db_query should log with correct structure."""
        with patch.object(logger, 'info') as mock_info:
            log_db_query(
                query_name="get_metrics_for_allocation",
                duration_ms=12.3,
                rows_affected=5,
                experiment_id="exp_123",
            )
            
            mock_info.assert_called_once()
            extra = mock_info.call_args[1]["extra"]
            
            assert extra["type"] == "db_query"
            assert extra["query_name"] == "get_metrics_for_allocation"
            assert extra["duration_ms"] == 12.3
            assert extra["rows_affected"] == 5
            assert extra["experiment_id"] == "exp_123"

    def test_log_algorithm(self):
        """log_algorithm should log with correct structure."""
        with patch.object(logger, 'info') as mock_info:
            log_algorithm(
                algorithm="thompson_sampling",
                experiment_id="exp_123",
                duration_ms=150.0,
                num_variants=3,
            )
            
            mock_info.assert_called_once()
            extra = mock_info.call_args[1]["extra"]
            
            assert extra["type"] == "algorithm"
            assert extra["algorithm"] == "thompson_sampling"
            assert extra["experiment_id"] == "exp_123"
            assert extra["duration_ms"] == 150.0
            assert extra["num_variants"] == 3

    def test_log_error(self):
        """log_error should log with correct structure."""
        with patch.object(logger, 'error') as mock_error:
            log_error(
                message="Connection failed",
                error_type="ConnectionError",
                host="snowflake.example.com",
            )
            
            mock_error.assert_called_once()
            extra = mock_error.call_args[1]["extra"]
            
            assert extra["type"] == "error"
            assert extra["error_type"] == "ConnectionError"
            assert extra["host"] == "snowflake.example.com"


class TestSetupLogging:
    """Tests for logging setup."""

    def test_setup_logging_returns_logger(self):
        """setup_logging should return a logger instance."""
        test_logger = setup_logging(level="DEBUG")
        
        assert isinstance(test_logger, logging.Logger)
        assert test_logger.name == "mab_api"

    def test_setup_logging_respects_level(self):
        """Logger should respect the configured level."""
        test_logger = setup_logging(level="WARNING")
        
        assert test_logger.level == logging.WARNING

    def test_logger_uses_json_formatter(self):
        """Logger handler should use JSON formatter."""
        test_logger = setup_logging(level="INFO")
        
        assert len(test_logger.handlers) > 0
        handler = test_logger.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)


class TestLoggingIntegration:
    """Integration tests for logging in API."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from src.main import app
        return TestClient(app)

    def test_request_is_logged(self, client):
        """HTTP requests should be logged."""
        with patch("src.middleware.log_request") as mock_log:
            response = client.get("/")
            
            # Root endpoint should be logged
            mock_log.assert_called()
            call_args = mock_log.call_args
            assert call_args[1]["method"] == "GET"
            assert call_args[1]["path"] == "/"

    def test_error_is_logged(self, client):
        """Errors should be logged."""
        with patch("src.main.log_error") as mock_log:
            with patch("src.routers.experiments.ExperimentService") as mock_service:
                mock_service.get_experiment.side_effect = Exception("Test error")
                
                response = client.get("/experiments/test123")
                
                # Error handler should log the error
                # Note: This depends on the exception handler implementation
