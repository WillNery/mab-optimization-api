"""Pydantic models for metrics."""

from datetime import date as date_type
from decimal import Decimal
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, model_validator


class MetricInput(BaseModel):
    """Schema for a single variant's metrics."""

    variant_name: str = Field(..., description="Name of the variant")
    sessions: int = Field(default=0, ge=0, description="Number of unique sessions")
    impressions: int = Field(..., ge=0, description="Number of impressions")
    clicks: int = Field(..., ge=0, description="Number of clicks")
    revenue: Decimal = Field(default=Decimal("0"), ge=0, description="Revenue in USD")

    @model_validator(mode="after")
    def validate_clicks_le_impressions(self) -> "MetricInput":
        """Ensure clicks do not exceed impressions."""
        if self.clicks > self.impressions:
            raise ValueError(
                f"Clicks ({self.clicks}) cannot exceed impressions ({self.impressions})"
            )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "variant_name": "control",
                    "sessions": 5000,
                    "impressions": 10000,
                    "clicks": 320,
                    "revenue": 150.50
                },
            ]
        }
    }


class MetricsBatchRequest(BaseModel):
    """Schema for batch metrics input."""

    date: date_type = Field(..., description="Date for the metrics (YYYY-MM-DD)")
    metrics: List[MetricInput] = Field(
        ..., min_length=1, description="List of metrics per variant"
    )
    source: Literal["api", "gam", "cdp", "manual"] = Field(
        default="api", description="Origin of the data"
    )
    batch_id: Optional[str] = Field(
        default=None, description="ID of the ingestion batch for traceability"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "date": "2025-01-15",
                    "metrics": [
                        {
                            "variant_name": "control",
                            "sessions": 5000,
                            "impressions": 10000,
                            "clicks": 320,
                            "revenue": 150.50
                        },
                        {
                            "variant_name": "variant_a",
                            "sessions": 5200,
                            "impressions": 10000,
                            "clicks": 420,
                            "revenue": 185.75
                        },
                    ],
                    "source": "gam",
                    "batch_id": "batch_20250115_001"
                }
            ]
        }
    }


class MetricsResponse(BaseModel):
    """Schema for metrics recording response."""

    message: str
    date: date_type
    variants_updated: int
    batch_id: Optional[str] = None
