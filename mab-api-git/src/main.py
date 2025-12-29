"""Multi-Armed Bandit Optimization API."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.routers import health_router, experiments_router
from src.config import settings
from src.logging_config import logger, log_error
from src.middleware import RequestLoggingMiddleware
from src.rate_limit import RateLimitMiddleware

# API metadata for documentation
app = FastAPI(
    title="Multi-Armed Bandit Optimization API",
    description="""
## Overview

API for optimizing A/B test traffic allocation using Multi-Armed Bandit algorithms.

## Algorithm

This API uses **Thompson Sampling** with a Beta-Bernoulli model to optimize CTR:

- **Prior**: Beta(1, 99) - Expected CTR ~1%
- **Posterior**: Beta(α + clicks, β + impressions - clicks)
- **Allocation**: Monte Carlo simulation to determine traffic split

## Workflow

1. **Create Experiment**: Define variants (control + treatments)
2. **Record Metrics**: Send daily aggregated data (sessions, impressions, clicks, revenue)
3. **Get Allocation**: Receive optimized traffic split for the next day

## Data Sources

This API is designed to receive data from:
- Google Ad Manager (GAM)
- Customer Data Platform (CDP)

Data should be aggregated by variant and day before sending to the API.

## Variant Attribution (CDP Responsibility)

Variant assignment should be done **by session** in the CDP layer:

```
User → CDP generates session_id → hash(session_id) % 100 → assigns variant
```

This ensures:
- Consistent user experience during navigation
- Accurate CTR measurement within sessions
- No dependency on user login

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| POST /experiments | 10/min |
| POST /metrics | 100/min |
| GET /allocation | 60/min |
| GET /history | 60/min |
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add middlewares (order matters: first added = last executed)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# Log startup
logger.info(
    "API starting",
    extra={
        "type": "startup",
        "host": settings.api_host,
        "port": settings.api_port,
        "snowflake_account": settings.snowflake_account,
        "default_window_days": settings.default_window_days,
        "thompson_samples": settings.thompson_samples,
    },
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    log_error(
        message=f"Unhandled exception: {str(exc)}",
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# Include routers
app.include_router(health_router)
app.include_router(experiments_router)


# Root endpoint
@app.get("/", include_in_schema=False)
async def root():
    """Redirect to documentation."""
    return {
        "message": "Multi-Armed Bandit Optimization API",
        "docs": "/docs",
        "health": "/health",
    }


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown."""
    logger.info("API shutting down", extra={"type": "shutdown"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
