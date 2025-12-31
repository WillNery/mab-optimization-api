"""Multi-Armed Bandit Optimization API."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.routers import health_router, experiments_router
from src.config import settings
from src.rate_limit import RateLimitMiddleware
from src.middleware import RequestLoggingMiddleware

# API metadata for documentation
app = FastAPI(
    title="Multi-Armed Bandit Optimization API",
    description="""
## Overview

API for optimizing A/B test traffic allocation using Multi-Armed Bandit algorithms.

## Algorithm

This API uses **Thompson Sampling** with a Beta-Bernoulli model to optimize CTR:

- **Prior**: Beta(1, 99) - Informative prior assuming ~1% CTR baseline
- **Posterior**: Beta(α₀ + clicks, β₀ + impressions - clicks)
- **Allocation**: Monte Carlo simulation to determine traffic split

## Workflow

1. **Create Experiment**: Define variants (control + treatments)
2. **Record Metrics**: Send daily aggregated data (impressions, clicks)
3. **Get Allocation**: Receive optimized traffic split for the next day

## Data Sources

This API is designed to receive data from:
- Google Ad Manager (GAM)
- Customer Data Platform (CDP)

Data should be aggregated by variant and day before sending to the API.

## Session Attribution

Variant assignment should be done **by session** (not by pageview or user) to ensure:
- Consistent user experience during navigation
- Accurate CTR measurement within sessions
- No dependency on user login

## Rate Limits

- **Per-minute limits**: Vary by endpoint (see headers)
- **Daily limit**: 3000 allocation calculations per day (cost protection)

Response headers include:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining in window
- `X-RateLimit-Reset`: Seconds until window resets
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# Add middlewares (order matters - first added is outermost)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    from src.logging_config import log_error
    
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


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
