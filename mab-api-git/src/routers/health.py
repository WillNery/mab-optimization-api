"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Health Check",
    description="Check if the API is running",
)
async def health_check():
    """Return health status of the API."""
    return {"status": "healthy", "service": "mab-api"}
