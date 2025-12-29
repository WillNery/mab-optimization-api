"""Request logging middleware."""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.logging_config import log_request, log_error


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all HTTP requests with timing and metadata.
    
    Logs:
    - Method, path, status code
    - Duration in milliseconds
    - Client IP
    - User agent
    - Request ID (if provided)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for health checks to reduce noise
        if request.url.path == "/health":
            return await call_next(request)

        start_time = time.perf_counter()
        
        # Extract metadata
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"
        
        request_id = request.headers.get("X-Request-ID", "")
        user_agent = request.headers.get("User-Agent", "")

        # Process request
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            log_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                request_id=request_id,
                user_agent=user_agent[:100],  # Truncate long user agents
                query_params=str(request.query_params) if request.query_params else None,
            )

            # Add request ID to response if provided
            if request_id:
                response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            log_error(
                message=f"Request failed: {str(e)}",
                error_type=type(e).__name__,
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                client_ip=client_ip,
                request_id=request_id,
            )
            raise
