"""Pydantic models for allocation responses."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ConfidenceInterval(BaseModel):
    """95% confidence interval."""
    
    lower: float = Field(..., description="Lower bound (2.5 percentile)")
    upper: float = Field(..., description="Upper bound (97.5 percentile)")


class VariantMetrics(BaseModel):
    """
    Metrics for a single variant.
    
    Campos obrigatórios: impressions, clicks, ctr
    Campos opcionais: sessions, revenue, ctr_ci, rps, rpm
    """

    impressions: int = Field(..., description="Total impressions in the window")
    clicks: int = Field(..., description="Total clicks in the window")
    ctr: float = Field(..., description="Click-through rate (clicks/impressions)")
    
    # Campos opcionais - podem não estar disponíveis dependendo da fonte de dados
    sessions: Optional[int] = Field(default=None, description="Total sessions in the window")
    revenue: Optional[Decimal] = Field(default=None, description="Total revenue in the window (USD)")
    ctr_ci: Optional[ConfidenceInterval] = Field(default=None, description="95% CI for CTR (Wilson Score)")
    rps: Optional[float] = Field(default=None, description="Revenue per session (revenue/sessions)")
    rpm: Optional[float] = Field(default=None, description="Revenue per mille (revenue/impressions * 1000)")


class VariantAllocation(BaseModel):
    """Allocation for a single variant."""

    variant_name: str = Field(..., description="Name of the variant")
    is_control: bool = Field(..., description="Whether this is the control variant")
    allocation_percentage: float = Field(
        ..., ge=0, le=100, description="Recommended traffic allocation percentage"
    )
    metrics: VariantMetrics = Field(..., description="Metrics for this variant")


class AllocationResponse(BaseModel):
    """Schema for allocation response."""

    experiment_id: str = Field(..., description="Experiment ID")
    experiment_name: str = Field(..., description="Experiment name")
    computed_at: datetime = Field(..., description="Timestamp when allocation was computed")
    algorithm: str = Field(default="thompson_sampling", description="Algorithm used")
    optimization_target: Literal["ctr", "rps", "rpm"] = Field(
        default="ctr", description="Metric being optimized"
    )
    window_days: int = Field(..., description="Number of days used for calculation")
    allocations: list[VariantAllocation] = Field(
        ..., description="Allocation per variant"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "experiment_id": "exp_abc123",
                    "experiment_name": "homepage_cta_test",
                    "computed_at": "2025-01-16T00:00:00Z",
                    "algorithm": "thompson_sampling",
                    "optimization_target": "ctr",
                    "window_days": 14,
                    "allocations": [
                        {
                            "variant_name": "control",
                            "is_control": True,
                            "allocation_percentage": 35.2,
                            "metrics": {
                                "impressions": 140000,
                                "clicks": 4480,
                                "ctr": 0.032,
                            },
                        },
                        {
                            "variant_name": "variant_a",
                            "is_control": False,
                            "allocation_percentage": 64.8,
                            "metrics": {
                                "impressions": 140000,
                                "clicks": 5880,
                                "ctr": 0.042,
                            },
                        },
                    ],
                }
            ]
        }
    }
