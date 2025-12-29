"""Structured logging configuration."""

import logging
import json
import sys
from datetime import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for observability tools (Datadog, CloudWatch, etc)."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields (from logger.info("msg", extra={...}))
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "taskName", "message",
            ]:
                log_entry[key] = value

        return json.dumps(log_entry)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Setup structured JSON logging.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("mab_api")
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler with JSON formatting
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


# Global logger instance
logger = setup_logging()


def log_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **extra: Any,
) -> None:
    """Log HTTP request with structured data."""
    logger.info(
        f"{method} {path} {status_code}",
        extra={
            "type": "http_request",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            **extra,
        },
    )


def log_db_query(
    query_name: str,
    duration_ms: float,
    rows_affected: int = 0,
    **extra: Any,
) -> None:
    """Log database query with structured data."""
    logger.info(
        f"DB query: {query_name}",
        extra={
            "type": "db_query",
            "query_name": query_name,
            "duration_ms": round(duration_ms, 2),
            "rows_affected": rows_affected,
            **extra,
        },
    )


def log_algorithm(
    algorithm: str,
    experiment_id: str,
    duration_ms: float,
    **extra: Any,
) -> None:
    """Log algorithm execution with structured data."""
    logger.info(
        f"Algorithm: {algorithm}",
        extra={
            "type": "algorithm",
            "algorithm": algorithm,
            "experiment_id": experiment_id,
            "duration_ms": round(duration_ms, 2),
            **extra,
        },
    )


def log_error(
    message: str,
    error_type: str,
    **extra: Any,
) -> None:
    """Log error with structured data."""
    logger.error(
        message,
        extra={
            "type": "error",
            "error_type": error_type,
            **extra,
        },
    )
