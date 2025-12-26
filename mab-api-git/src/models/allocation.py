"""Pydantic models for allocation responses."""

from datetime import datetime

from pydantic import BaseModel, Field


class VariantMetrics(BaseModel):
    """Metrics for a single variant."""

    impressions: int = Field(..., description="Total impressions in the window")
    clicks: int = Field(..., description="Total clicks in the window")
    ctr: float = Field(..., description="Click-through rate (clicks/impressions)")


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
                    "window_days": 14,
                    "allocations": [
                        {
                            "variant_name": "control",
                            "is_control": True,
                            "allocation_percentage": 5.2,
                            "metrics": {
                                "impressions": 140000,
                                "clicks": 4480,
                                "ctr": 0.032,
                            },
                        },
                        {
                            "variant_name": "variant_a",
                            "is_control": False,
                            "allocation_percentage": 65.3,
                            "metrics": {
                                "impressions": 140000,
                                "clicks": 5880,
                                "ctr": 0.042,
                            },
                        },
                        {
                            "variant_name": "variant_b",
                            "is_control": False,
                            "allocation_percentage": 29.5,
                            "metrics": {
                                "impressions": 140000,
                                "clicks": 5320,
                                "ctr": 0.038,
                            },
                        },
                    ],
                }
            ]
        }
    }
