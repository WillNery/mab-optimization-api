"""Pydantic models for experiments and variants."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class VariantCreate(BaseModel):
    """Schema for creating a variant."""

    name: str = Field(..., min_length=1, max_length=100, description="Variant name")
    is_control: bool = Field(default=False, description="Whether this is the control variant")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"name": "control", "is_control": True},
                {"name": "variant_a", "is_control": False},
            ]
        }
    }


class VariantResponse(BaseModel):
    """Schema for variant response."""

    id: str
    name: str
    is_control: bool
    created_at: datetime


class ExperimentCreate(BaseModel):
    """Schema for creating an experiment."""

    name: str = Field(..., min_length=1, max_length=255, description="Experiment name")
    description: Optional[str] = Field(None, description="Experiment description")
    variants: list[VariantCreate] = Field(
        ..., min_length=2, description="List of variants (minimum 2)"
    )

    @model_validator(mode="after")
    def validate_has_control(self) -> "ExperimentCreate":
        """Ensure at least one variant is marked as control."""
        has_control = any(v.is_control for v in self.variants)
        if not has_control:
            raise ValueError("At least one variant must be marked as control (is_control=True)")
        return self

    @model_validator(mode="after")
    def validate_unique_names(self) -> "ExperimentCreate":
        """Ensure variant names are unique within the experiment."""
        names = [v.name for v in self.variants]
        if len(names) != len(set(names)):
            raise ValueError("Variant names must be unique within an experiment")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "homepage_cta_test",
                    "description": "Testing CTA button variants on homepage",
                    "variants": [
                        {"name": "control", "is_control": True},
                        {"name": "variant_a", "is_control": False},
                        {"name": "variant_b", "is_control": False},
                    ],
                }
            ]
        }
    }


class ExperimentResponse(BaseModel):
    """Schema for experiment response."""

    id: str
    name: str
    description: Optional[str]
    status: str
    variants: list[VariantResponse]
    created_at: datetime
    updated_at: datetime
