"""Thompson Sampling implementation for Multi-Armed Bandit."""

from dataclasses import dataclass
from datetime import datetime
import time
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
from src.logging_config import log_algorithm


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
    - Prior: Beta(α₀, β₀) where α₀=1, β₀=99 (expected CTR ~1%)
    - Likelihood: Bernoulli (click or no click)
    - Posterior: Beta(alpha, beta) where:
        - alpha = α₀ + clicks
        - beta = β₀ + impressions - clicks
    
    Allocation is determined by simulating many draws from each variant's
    posterior and counting how often each variant has the highest sampled CTR.
    """

    def __init__(
        self,
        n_samples: int | None = None,
        prior_alpha: int | None = None,
        prior_beta: int | None = None,
    ):
        """
        Initialize the Thompson Sampling engine.
        
        Args:
            n_samples: Number of Monte Carlo samples (default from settings)
            prior_alpha: Prior α parameter (default from settings)
            prior_beta: Prior β parameter (default from settings)
        """
        self.n_samples = n_samples or settings.thompson_samples
        self.prior_alpha = prior_alpha or settings.prior_alpha
        self.prior_beta = prior_beta or settings.prior_beta

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
        self.min_impressions = settings.min_impressions
        self.default_window = settings.default_window_days
        self.max_window = settings.max_window_days

    def get_allocation(
        self,
        experiment_id: str,
        window_days: int | None = None,
    ) -> Optional[AllocationResponse]:
        """
        Get optimized traffic allocation for an experiment.
        
        Logic:
        1. Collect metrics from last `window_days` days (default 14)
        2. If any variant has < MIN_IMPRESSIONS, expand window to max (30 days)
        3. If still < MIN_IMPRESSIONS, use fallback (prior only)
        
        Args:
            experiment_id: Experiment UUID
            window_days: Number of days to look back (default: 14)
            
        Returns:
            Allocation response or None if experiment not found
        """
        start_time = time.time()
        
        if window_days is None:
            window_days = self.default_window

        # Get experiment
        experiment = ExperimentRepository.get_experiment_by_id(experiment_id)
        if not experiment:
            return None

        # Get metrics with initial window
        metrics_data = MetricsRepository.get_metrics_for_allocation(
            experiment_id=experiment_id,
            window_days=window_days,
        )

        # Check if any variant has insufficient data
        min_variant_impressions = min(
            (int(m["impressions"]) for m in metrics_data),
            default=0
        )
        
        # Track if we used fallback
        used_fallback = False
        actual_window = window_days
        
        # If insufficient data and not already at max window, expand
        if min_variant_impressions < self.min_impressions and window_days < self.max_window:
            actual_window = self.max_window
            metrics_data = MetricsRepository.get_metrics_for_allocation(
                experiment_id=experiment_id,
                window_days=self.max_window,
            )
            min_variant_impressions = min(
                (int(m["impressions"]) for m in metrics_data),
                default=0
            )

        # If still insufficient, mark as fallback (will use prior only)
        if min_variant_impressions < self.min_impressions:
            used_fallback = True

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

        # Build algorithm description
        algorithm_desc = "thompson_sampling"
        if used_fallback:
            algorithm_desc += " (fallback: prior only)"

        # Log algorithm execution
        duration_ms = (time.time() - start_time) * 1000
        log_algorithm(
            algorithm="thompson_sampling",
            experiment_id=experiment_id,
            duration_ms=duration_ms,
            n_samples=self.engine.n_samples,
            num_variants=len(variants),
            total_impressions=sum(v.impressions for v in variants),
            window_days=actual_window,
            used_fallback=used_fallback,
        )

        return AllocationResponse(
            experiment_id=experiment_id,
            experiment_name=experiment["name"],
            computed_at=datetime.utcnow(),
            algorithm=algorithm_desc,
            window_days=actual_window,
            allocations=variant_allocations,
        )
