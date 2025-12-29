"""Rate limiting middleware and utilities."""

import time
from collections import defaultdict
from typing import Callable, Optional
from functools import wraps

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.logging_config import logger


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    
    For production, consider Redis-based rate limiting for:
    - Distributed deployments
    - Persistence across restarts
    - Better memory management
    """

    def __init__(self):
        # Structure: {key: [(timestamp, count), ...]}
        self._requests: dict[str, list[tuple[float, int]]] = defaultdict(list)

    def _clean_old_requests(self, key: str, window_seconds: int) -> None:
        """Remove requests outside the current window."""
        now = time.time()
        cutoff = now - window_seconds
        self._requests[key] = [
            (ts, count) for ts, count in self._requests[key] if ts > cutoff
        ]

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """
        Check if request is allowed under rate limit.
        
        Args:
            key: Unique identifier (IP, API key, etc)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
        
        Returns:
            Tuple of (is_allowed, remaining_requests, reset_seconds)
        """
        now = time.time()
        self._clean_old_requests(key, window_seconds)

        total_requests = sum(count for _, count in self._requests[key])

        if total_requests >= max_requests:
            # Calculate reset time
            if self._requests[key]:
                oldest_ts = min(ts for ts, _ in self._requests[key])
                reset_seconds = int(oldest_ts + window_seconds - now)
            else:
                reset_seconds = window_seconds
            return False, 0, reset_seconds

        # Record this request
        self._requests[key].append((now, 1))
        remaining = max_requests - total_requests - 1

        return True, remaining, window_seconds


# Global rate limiter instance
rate_limiter = RateLimiter()


# Rate limit configurations per endpoint
RATE_LIMITS = {
    "POST /experiments": {"max_requests": 10, "window_seconds": 60},
    "POST /experiments/{experiment_id}/metrics": {"max_requests": 100, "window_seconds": 60},
    "GET /experiments/{experiment_id}/allocation": {"max_requests": 60, "window_seconds": 60},
    "GET /experiments/{experiment_id}/history": {"max_requests": 60, "window_seconds": 60},
    "GET /experiments/{experiment_id}": {"max_requests": 120, "window_seconds": 60},
    "default": {"max_requests": 100, "window_seconds": 60},
}


def get_rate_limit_key(request: Request) -> str:
    """
    Generate rate limit key from request.
    
    Uses X-Forwarded-For header if behind proxy, otherwise client IP.
    In production, consider using API key or user ID.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take first IP if multiple proxies
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_endpoint_pattern(request: Request) -> str:
    """Convert request to endpoint pattern for rate limit lookup."""
    method = request.method
    path = request.url.path

    # Normalize path patterns
    parts = path.strip("/").split("/")
    normalized_parts = []
    for i, part in enumerate(parts):
        # Check if this looks like an ID (UUID-like or numeric)
        if len(part) == 36 and "-" in part:  # UUID
            if i > 0 and normalized_parts:
                normalized_parts.append("{experiment_id}")
            else:
                normalized_parts.append(part)
        else:
            normalized_parts.append(part)

    normalized_path = "/" + "/".join(normalized_parts)
    return f"{method} {normalized_path}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to apply rate limiting to all requests.
    
    Adds headers:
    - X-RateLimit-Limit: Maximum requests allowed
    - X-RateLimit-Remaining: Requests remaining in window
    - X-RateLimit-Reset: Seconds until window resets
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json", "/"]:
            return await call_next(request)

        # Get rate limit config for endpoint
        endpoint_pattern = get_endpoint_pattern(request)
        config = RATE_LIMITS.get(endpoint_pattern, RATE_LIMITS["default"])

        # Check rate limit
        key = get_rate_limit_key(request)
        full_key = f"{key}:{endpoint_pattern}"

        is_allowed, remaining, reset = rate_limiter.is_allowed(
            full_key,
            config["max_requests"],
            config["window_seconds"],
        )

        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded for {key}",
                extra={
                    "type": "rate_limit",
                    "key": key,
                    "endpoint": endpoint_pattern,
                    "limit": config["max_requests"],
                    "window_seconds": config["window_seconds"],
                },
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": config["max_requests"],
                    "window_seconds": config["window_seconds"],
                    "retry_after": reset,
                },
                headers={
                    "X-RateLimit-Limit": str(config["max_requests"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                    "Retry-After": str(reset),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(config["max_requests"])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)

        return response
