"""Experiment endpoints."""

from fastapi import APIRouter, HTTPException, Query

from src.models.experiment import ExperimentCreate, ExperimentResponse
from src.models.metrics import MetricsBatchRequest, MetricsResponse
from src.models.allocation import AllocationResponse
from src.services.experiment import ExperimentService
from src.services.allocation import AllocationService
from src.config import settings

router = APIRouter(prefix="/experiments", tags=["Experiments"])


@router.post(
    "",
    response_model=ExperimentResponse,
    status_code=201,
    summary="Create Experiment",
    description="Create a new A/B test experiment with variants",
)
async def create_experiment(data: ExperimentCreate):
    """
    Create a new experiment with its variants.
    
    - At least 2 variants are required
    - At least one variant must be marked as control (is_control=True)
    - Variant names must be unique within the experiment
    """
    try:
        return ExperimentService.create_experiment(data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Get Experiment",
    description="Get experiment details by ID",
)
async def get_experiment(experiment_id: str):
    """Get experiment details including all variants."""
    result = ExperimentService.get_experiment(experiment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.post(
    "/{experiment_id}/metrics",
    response_model=MetricsResponse,
    status_code=201,
    summary="Record Metrics",
    description="Record daily metrics for experiment variants",
)
async def record_metrics(experiment_id: str, data: MetricsBatchRequest):
    """
    Record metrics (impressions and clicks) for each variant.
    
    This endpoint accepts aggregated daily data from GAM/CDP sources.
    Data is stored in both raw (audit) and daily (clean) tables.
    """
    try:
        return ExperimentService.record_metrics(experiment_id, data)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{experiment_id}/allocation",
    response_model=AllocationResponse,
    summary="Get Allocation",
    description="Get optimized traffic allocation for the next day",
)
async def get_allocation(
    experiment_id: str,
    window_days: int = Query(
        default=None,
        ge=1,
        le=90,
        description=f"Number of days to analyze (default: {settings.default_window_days})",
    ),
):
    """
    Calculate optimized traffic allocation using Thompson Sampling.
    
    The algorithm:
    1. Aggregates metrics from the last N days (default: 14)
    2. Computes Beta distribution parameters for each variant
    3. Runs Monte Carlo simulation to determine allocation
    
    Variants with higher CTR will receive more traffic allocation,
    while still exploring underperforming variants.
    """
    service = AllocationService()
    result = service.get_allocation(experiment_id, window_days)
    if not result:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.get(
    "/{experiment_id}/history",
    summary="Get Metrics History",
    description="Get historical metrics for an experiment",
)
async def get_history(experiment_id: str):
    """
    Get daily metrics history for all variants.
    
    Returns time series data useful for visualization and debugging.
    """
    from src.repositories.metrics import MetricsRepository
    from src.repositories.experiment import ExperimentRepository

    # Verify experiment exists
    experiment = ExperimentRepository.get_experiment_by_id(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    history = MetricsRepository.get_metrics_history(experiment_id)
    
    return {
        "experiment_id": experiment_id,
        "experiment_name": experiment["name"],
        "history": history,
    }
