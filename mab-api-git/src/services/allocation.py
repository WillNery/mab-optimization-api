"""Thompson Sampling implementation for Multi-Armed Bandit."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal

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
    data_source: Literal["observed", "fallback"]  # Indica se usou dados ou prior


class ThompsonSamplingEngine:
    """
    Thompson Sampling implementation for CTR optimization.
    
    Uses Beta-Bernoulli conjugate model:
    - Prior: Beta(α₀, β₀) where α₀=1, β₀=99 (expected CTR ~1%)
    - Likelihood: Bernoulli (click or no click)
    - Posterior: Beta(α₀ + clicks, β₀ + impressions - clicks)
    
    Features:
    - Informative prior for cold start (not uniform)
    - Minimum impressions threshold for statistical reliability
    - Automatic window expansion when data is insufficient
    
    Allocation is determined by simulating many draws from each variant's
    posterior and counting how often each variant has the highest sampled CTR.
    """

    def __init__(
        self,
        n_samples: int | None = None,
        prior_alpha: int | None = None,
        prior_beta: int | None = None,
        min_impressions: int | None = None,
    ):
        """
        Initialize the Thompson Sampling engine.
        
        Args:
            n_samples: Number of Monte Carlo samples (default from settings)
            prior_alpha: Alpha parameter for Beta prior (default from settings)
            prior_beta: Beta parameter for Beta prior (default from settings)
            min_impressions: Minimum impressions for reliable estimation
        """
        self.n_samples = n_samples or settings.thompson_samples
        self.prior_alpha = prior_alpha or settings.prior_alpha
        self.prior_beta = prior_beta or settings.prior_beta
        self.min_impressions = min_impressions or settings.min_impressions

    def compute_beta_params(self, clicks: int, impressions: int) -> tuple[int, int]:
        """
        Compute Beta distribution parameters using Bayesian update.
        
        Posterior = Prior × Likelihood
        Beta(α₀ + clicks, β₀ + impressions - clicks)
        
        Args:
            clicks: Number of clicks observed
            impressions: Number of impressions observed
            
        Returns:
            Tuple of (alpha, beta) for the posterior distribution
        """
        alpha = self.prior_alpha + clicks
        beta = self.prior_beta + impressions - clicks
        return alpha, beta

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
    """Service for computing traffic allocations with adaptive windowing."""

    def __init__(self):
        self.engine = ThompsonSamplingEngine()

    def _has_sufficient_data(self, variants: list[VariantData]) -> bool:
        """
        Check if all variants have minimum required impressions.
        
        Args:
            variants: List of variant data
            
        Returns:
            True if all variants have >= min_impressions
        """
        if not variants:
            return False
        return all(v.impressions >= self.engine.min_impressions for v in variants)

    def _get_metrics_with_window(
        self,
        experiment_id: str,
        window_days: int,
    ) -> list[dict]:
        """
        Get metrics for a specific window.
        
        Args:
            experiment_id: Experiment UUID
            window_days: Number of days to look back
            
        Returns:
            List of metrics dicts from repository
        """
        return MetricsRepository.get_metrics_for_allocation(
            experiment_id=experiment_id,
            window_days=window_days,
        )

    def _convert_to_variant_data(
        self,
        metrics_data: list[dict],
        use_fallback: bool = False,
    ) -> list[VariantData]:
        """
        Convert raw metrics to VariantData objects with proper Beta parameters.
        
        Args:
            metrics_data: Raw metrics from repository
            use_fallback: If True, use only prior (ignore observed data)
            
        Returns:
            List of VariantData objects
        """
        variants = []
        
        for m in metrics_data:
            impressions = int(m["impressions"])
            clicks = int(m["clicks"])
            
            if use_fallback or impressions < self.engine.min_impressions:
                # Use only prior (fallback mode)
                alpha = self.engine.prior_alpha
                beta = self.engine.prior_beta
                data_source = "fallback"
                # CTR is expected value of prior
                ctr = alpha / (alpha + beta)
            else:
                # Use observed data with prior (Bayesian update)
                alpha, beta = self.engine.compute_beta_params(clicks, impressions)
                data_source = "observed"
                ctr = clicks / impressions if impressions > 0 else 0.0
            
            variants.append(
                VariantData(
                    variant_id=m["variant_id"],
                    variant_name=m["variant_name"],
                    is_control=m["is_control"],
                    impressions=impressions,
                    clicks=clicks,
                    ctr=ctr,
                    beta_alpha=alpha,
                    beta_beta=beta,
                    data_source=data_source,
                )
            )
        
        return variants

    def get_allocation(
        self,
        experiment_id: str,
        window_days: int | None = None,
    ) -> Optional[AllocationResponse]:
        """
        Get optimized traffic allocation for an experiment.
        
        Logic:
        1. Try with default window (14 days)
        2. If any variant has < min_impressions, expand to max_window (30 days)
        3. If still insufficient, use fallback (prior only)
        
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

        # Step 1: Try with requested window
        metrics_data = self._get_metrics_with_window(experiment_id, window_days)
        variants = self._convert_to_variant_data(metrics_data, use_fallback=False)
        
        actual_window = window_days
        used_fallback = False

        # Step 2: If insufficient data, try expanding window
        if not self._has_sufficient_data(variants):
            if window_days < settings.max_window_days:
                # Expand to max window
                metrics_data = self._get_metrics_with_window(
                    experiment_id, 
                    settings.max_window_days
                )
                variants = self._convert_to_variant_data(metrics_data, use_fallback=False)
                actual_window = settings.max_window_days
        
        # Step 3: If still insufficient, use fallback
        if not self._has_sufficient_data(variants):
            variants = self._convert_to_variant_data(metrics_data, use_fallback=True)
            used_fallback = True

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

        # Determine algorithm description
        if used_fallback:
            algorithm = "thompson_sampling (fallback: prior only)"
        else:
            algorithm = "thompson_sampling"

        return AllocationResponse(
            experiment_id=experiment_id,
            experiment_name=experiment["name"],
            computed_at=datetime.utcnow(),
            algorithm=algorithm,
            window_days=actual_window,
            allocations=variant_allocations,
        )
