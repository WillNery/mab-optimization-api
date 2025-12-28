"""Thompson Sampling implementation for Multi-Armed Bandit."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
    ConfidenceInterval,
)


@dataclass # cria uma classe que guarda os dados
class VariantData:
    """Internal representation of variant data for Thompson Sampling."""
    
    variant_id: str
    variant_name: str
    is_control: bool
    sessions: int
    impressions: int
    clicks: int
    revenue: Decimal
    ctr: float
    ctr_ci_lower: float
    ctr_ci_upper: float
    rps: float
    rpm: float
    # Thompson Sampling parameters
    alpha: float
    beta: float
    data_source: Literal["observed", "fallback"]


class ThompsonSamplingEngine:
    """
    Thompson Sampling implementation for metric optimization.
    
    Supports multiple optimization targets:
    - CTR (Click-Through Rate): clicks / impressions
    - RPS (Revenue Per Session): revenue / sessions
    - RPM (Revenue Per Mille): revenue / impressions * 1000
    
    For CTR: Uses Beta-Bernoulli conjugate model
    For RPS/RPM: Uses Normal approximation with empirical mean/variance
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
            n_samples: Number of Monte Carlo samples
            prior_alpha: Alpha parameter for Beta prior (CTR)
            prior_beta: Beta parameter for Beta prior (CTR)
            min_impressions: Minimum impressions for reliable estimation
        """
        self.n_samples = n_samples or settings.thompson_samples
        self.prior_alpha = prior_alpha or settings.prior_alpha
        self.prior_beta = prior_beta or settings.prior_beta
        self.min_impressions = min_impressions or settings.min_impressions

    def compute_beta_params_ctr(self, clicks: int, impressions: int) -> tuple[float, float]:
        """
        Compute Beta distribution parameters for CTR.
        
        Posterior = Prior × Likelihood
        Beta(α₀ + clicks, β₀ + impressions - clicks)
        """
        alpha = self.prior_alpha + clicks
        beta = self.prior_beta + impressions - clicks
        return float(alpha), float(beta)

    def compute_normal_params_revenue(
        self, 
        revenue: float, 
        count: int,
        prior_mean: float = 0.01,
        prior_variance: float = 0.01,
    ) -> tuple[float, float]:
        """
        Compute Normal distribution parameters for revenue metrics.
        
        Uses empirical mean and variance with prior.
        
        Args:
            revenue: Total revenue
            count: Number of sessions or impressions
            prior_mean: Prior expected value
            prior_variance: Prior variance
            
        Returns:
            (mean, std) for Normal distribution
        """
        if count == 0:
            return prior_mean, np.sqrt(prior_variance)
        
        observed_mean = revenue / count
        # Use prior to stabilize variance estimation
        # Bayesian update with conjugate prior
        posterior_mean = (prior_mean + observed_mean * count) / (1 + count)
        posterior_variance = prior_variance / (1 + count)
        
        return posterior_mean, np.sqrt(max(posterior_variance, 1e-10))

    def calculate_allocation(
        self, 
        variants: list[VariantData],
        optimization_target: Literal["ctr", "rps", "rpm"] = "ctr",
    ) -> dict[str, float]:
        """
        Calculate traffic allocation using Thompson Sampling.
        
        Args:
            variants: List of variant data
            optimization_target: Metric to optimize
            
        Returns:
            Dict mapping variant_name to allocation percentage
        """
        if not variants:
            return {}

        # Sample from appropriate distribution based on optimization target
        if optimization_target == "ctr":
            samples = self._sample_ctr(variants)
        else:
            samples = self._sample_revenue(variants, optimization_target)

        # Count wins for each variant
        wins = {v.variant_name: 0 for v in variants}
        
        for i in range(self.n_samples):
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

        # Ensure allocations sum to 100%
        total = sum(allocations.values())
        if total != 100.0:
            max_variant = max(allocations, key=allocations.get)
            allocations[max_variant] += round(100.0 - total, 2)

        return allocations

    def _sample_ctr(self, variants: list[VariantData]) -> dict[str, np.ndarray]:
        """Sample from Beta distribution for CTR optimization."""
        return {
            v.variant_name: stats.beta.rvs(
                v.alpha,
                v.beta,
                size=self.n_samples,
            )
            for v in variants
        }

    def _sample_revenue(
        self, 
        variants: list[VariantData],
        metric: Literal["rps", "rpm"],
    ) -> dict[str, np.ndarray]:
        """Sample from Normal distribution for revenue optimization."""
        samples = {}
        
        for v in variants:
            if metric == "rps":
                mean, std = self.compute_normal_params_revenue(
                    float(v.revenue), v.sessions
                )
            else:  # rpm
                mean, std = self.compute_normal_params_revenue(
                    float(v.revenue) * 1000, v.impressions
                )
            
            # Sample from Normal, clip to non-negative
            raw_samples = stats.norm.rvs(mean, std, size=self.n_samples)
            samples[v.variant_name] = np.clip(raw_samples, 0, None)
        
        return samples


class AllocationService:
    """Service for computing traffic allocations with adaptive windowing."""

    def __init__(self):
        self.engine = ThompsonSamplingEngine()

    def _has_sufficient_data(self, variants: list[VariantData]) -> bool:
        """Check if all variants have minimum required impressions."""
        if not variants:
            return False
        return all(v.impressions >= self.engine.min_impressions for v in variants)

    def _get_metrics_with_window(
        self,
        experiment_id: str,
        window_days: int,
    ) -> list[dict]:
        """Get metrics for a specific window."""
        return MetricsRepository.get_metrics_for_allocation(
            experiment_id=experiment_id,
            window_days=window_days,
        )

    def _convert_to_variant_data(
        self,
        metrics_data: list[dict],
        optimization_target: str,
        use_fallback: bool = False,
    ) -> list[VariantData]:
        """
        Convert raw metrics to VariantData objects.
        
        Args:
            metrics_data: Raw metrics from repository
            optimization_target: Metric being optimized
            use_fallback: If True, use only prior
            
        Returns:
            List of VariantData objects
        """
        variants = []
        
        for m in metrics_data:
            sessions = int(m["sessions"])
            impressions = int(m["impressions"])
            clicks = int(m["clicks"])
            revenue = Decimal(str(m["revenue"]))
            
            # Get metrics from SQL (already calculated)
            ctr = float(m.get("ctr", 0))
            rps = float(m.get("rps", 0))
            rpm = float(m.get("rpm", 0))
            ctr_ci_lower = float(m.get("ctr_ci_lower", 0))
            ctr_ci_upper = float(m.get("ctr_ci_upper", 0))
            
            # Determine if using fallback
            if use_fallback or impressions < self.engine.min_impressions:
                data_source = "fallback"
                alpha = float(self.engine.prior_alpha)
                beta = float(self.engine.prior_beta)
            else:
                data_source = "observed"
                if optimization_target == "ctr":
                    alpha, beta = self.engine.compute_beta_params_ctr(clicks, impressions)
                else:
                    # For revenue metrics, alpha/beta are placeholders
                    # Actual sampling uses Normal distribution
                    alpha, beta = 1.0, 1.0
            
            variants.append(
                VariantData(
                    variant_id=m["variant_id"],
                    variant_name=m["variant_name"],
                    is_control=m["is_control"],
                    sessions=sessions,
                    impressions=impressions,
                    clicks=clicks,
                    revenue=revenue,
                    ctr=ctr,
                    ctr_ci_lower=ctr_ci_lower,
                    ctr_ci_upper=ctr_ci_upper,
                    rps=rps,
                    rpm=rpm,
                    alpha=alpha,
                    beta=beta,
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
        1. Get experiment and its optimization target
        2. Try with default window (14 days)
        3. If insufficient data, expand to max_window (30 days)
        4. If still insufficient, use fallback
        5. Calculate allocation using appropriate metric
        
        Args:
            experiment_id: Experiment UUID
            window_days: Number of days to look back
            
        Returns:
            Allocation response or None if experiment not found
        """
        if window_days is None:
            window_days = settings.default_window_days

        # Get experiment
        experiment = ExperimentRepository.get_experiment_by_id(experiment_id)
        if not experiment:
            return None

        optimization_target = experiment.get("optimization_target", "ctr")

        # Step 1: Try with requested window
        metrics_data = self._get_metrics_with_window(experiment_id, window_days)
        variants = self._convert_to_variant_data(
            metrics_data, optimization_target, use_fallback=False
        )
        
        actual_window = window_days
        used_fallback = False

        # Step 2: If insufficient data, try expanding window
        if not self._has_sufficient_data(variants):
            if window_days < settings.max_window_days:
                metrics_data = self._get_metrics_with_window(
                    experiment_id, 
                    settings.max_window_days
                )
                variants = self._convert_to_variant_data(
                    metrics_data, optimization_target, use_fallback=False
                )
                actual_window = settings.max_window_days
        
        # Step 3: If still insufficient, use fallback
        if not self._has_sufficient_data(variants):
            variants = self._convert_to_variant_data(
                metrics_data, optimization_target, use_fallback=True
            )
            used_fallback = True

        # Calculate allocation
        allocations = self.engine.calculate_allocation(variants, optimization_target)

        # Build response
        variant_allocations = []
        for v in variants:
            variant_allocations.append(
                VariantAllocation(
                    variant_name=v.variant_name,
                    is_control=v.is_control,
                    allocation_percentage=allocations.get(v.variant_name, 0.0),
                    metrics=VariantMetrics(
                        sessions=v.sessions,
                        impressions=v.impressions,
                        clicks=v.clicks,
                        revenue=v.revenue,
                        ctr=round(v.ctr, 6),
                        ctr_ci=ConfidenceInterval(
                            lower=round(v.ctr_ci_lower, 6),
                            upper=round(v.ctr_ci_upper, 6),
                        ),
                        rps=round(v.rps, 6),
                        rpm=round(v.rpm, 6),
                    ),
                )
            )

        # Sort: control first, then by allocation descending
        variant_allocations.sort(
            key=lambda x: (-x.is_control, -x.allocation_percentage)
        )

        # Determine algorithm description
        if used_fallback:
            algorithm = f"thompson_sampling (fallback: prior only, target: {optimization_target})"
        else:
            algorithm = f"thompson_sampling (target: {optimization_target})"

        return AllocationResponse(
            experiment_id=experiment_id,
            experiment_name=experiment["name"],
            computed_at=datetime.utcnow(),
            algorithm=algorithm,
            optimization_target=optimization_target,
            window_days=actual_window,
            allocations=variant_allocations,
        )
