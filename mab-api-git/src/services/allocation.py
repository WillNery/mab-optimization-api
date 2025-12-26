"""Thompson Sampling implementation for Multi-Armed Bandit."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
from scipy import stats

from src.config import settings
from src.repositories.experiment import ExperimentRepository
from src.repositories.metrics import MetricsRepository
from src.models.allocation import (
    AllocationResponse,
    VariantAllocation,
    VariantMetrics,
)


@dataclass
class VariantData:
    """Internal representation of variant data for Thompson Sampling."""
    
    variant_id: str
    variant_name: str
    is_control: bool
    impressions: int
    clicks: int
    ctr: float
    beta_alpha: int
    beta_beta: int


class ThompsonSamplingEngine:
    """
    Thompson Sampling implementation for CTR optimization.
    
    Uses Beta-Bernoulli conjugate model:
    - Prior: Beta(1, 1) = Uniform (no prior knowledge)
    - Likelihood: Bernoulli (click or no click)
    - Posterior: Beta(alpha, beta) where:
        - alpha = clicks + 1
        - beta = impressions - clicks + 1
    
    Allocation is determined by simulating many draws from each variant's
    posterior and counting how often each variant has the highest sampled CTR.
    """

    def __init__(self, n_samples: int | None = None):
        """
        Initialize the Thompson Sampling engine.
        
        Args:
            n_samples: Number of Monte Carlo samples (default from settings)
        """
        self.n_samples = n_samples or settings.thompson_samples

    def calculate_allocation(self, variants: list[VariantData]) -> dict[str, float]:
        """
        Calculate traffic allocation using Thompson Sampling.
        
        For each Monte Carlo simulation:
        1. Sample θ from Beta(alpha, beta) for each variant
        2. The variant with highest θ "wins"
        3. Allocation = proportion of wins for each variant
        
        Args:
            variants: List of variant data with beta parameters
            
        Returns:
            Dict mapping variant_name to allocation percentage
        """
        if not variants:
            return {}

        # Handle case with no data - return uniform allocation
        total_impressions = sum(v.impressions for v in variants)
        if total_impressions == 0:
            uniform_pct = round(100.0 / len(variants), 2)
            return {v.variant_name: uniform_pct for v in variants}

        # Sample from Beta distribution for each variant
        samples = {
            v.variant_name: stats.beta.rvs(
                v.beta_alpha,
                v.beta_beta,
                size=self.n_samples,
            )
            for v in variants
        }

        # Count wins for each variant
        wins = {v.variant_name: 0 for v in variants}
        
        for i in range(self.n_samples):
            # Find variant with highest sampled theta in this simulation
            best_variant = max(
                variants,
                key=lambda v: samples[v.variant_name][i],
            )
            wins[best_variant.variant_name] += 1

        # Convert wins to percentages
        allocations = {
            name: round((count / self.n_samples) * 100, 2)
            for name, count in wins.items()
        }

        # Ensure allocations sum to 100% (handle rounding)
        total = sum(allocations.values())
        if total != 100.0:
            # Adjust the largest allocation to make sum exactly 100
            max_variant = max(allocations, key=allocations.get)
            allocations[max_variant] += round(100.0 - total, 2)

        return allocations


class AllocationService:
    """Service for computing traffic allocations."""

    def __init__(self):
        self.engine = ThompsonSamplingEngine()

    def get_allocation(
        self,
        experiment_id: str,
        window_days: int | None = None,
    ) -> Optional[AllocationResponse]:
        """
        Get optimized traffic allocation for an experiment.
        
        Args:
            experiment_id: Experiment UUID
            window_days: Number of days to look back (default: 14)
            
        Returns:
            Allocation response or None if experiment not found
        """
        if window_days is None:
            window_days = settings.default_window_days

        # Get experiment
        experiment = ExperimentRepository.get_experiment_by_id(experiment_id)
        if not experiment:
            return None

        # Get metrics for allocation
        metrics_data = MetricsRepository.get_metrics_for_allocation(
            experiment_id=experiment_id,
            window_days=window_days,
        )

        # Convert to VariantData objects
        variants = [
            VariantData(
                variant_id=m["variant_id"],
                variant_name=m["variant_name"],
                is_control=m["is_control"],
                impressions=int(m["impressions"]),
                clicks=int(m["clicks"]),
                ctr=float(m["ctr"]),
                beta_alpha=int(m["beta_alpha"]),
                beta_beta=int(m["beta_beta"]),
            )
            for m in metrics_data
        ]

        # Calculate allocation
        allocations = self.engine.calculate_allocation(variants)

        # Build response
        variant_allocations = []
        for v in variants:
            variant_allocations.append(
                VariantAllocation(
                    variant_name=v.variant_name,
                    is_control=v.is_control,
                    allocation_percentage=allocations.get(v.variant_name, 0.0),
                    metrics=VariantMetrics(
                        impressions=v.impressions,
                        clicks=v.clicks,
                        ctr=round(v.ctr, 6),
                    ),
                )
            )

        # Sort: control first, then by allocation descending
        variant_allocations.sort(
            key=lambda x: (-x.is_control, -x.allocation_percentage)
        )

        return AllocationResponse(
            experiment_id=experiment_id,
            experiment_name=experiment["name"],
            computed_at=datetime.utcnow(),
            algorithm="thompson_sampling",
            window_days=window_days,
            allocations=variant_allocations,
        )
