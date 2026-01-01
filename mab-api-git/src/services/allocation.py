"""Thompson Sampling implementation for Multi-Armed Bandit."""

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, date
import time
from typing import Optional

import numpy as np
from scipy import stats

from src.config import settings
from src.repositories.experiment import ExperimentRepository
from src.repositories.metrics import MetricsRepository
from src.repositories.allocation_history import AllocationHistoryRepository
from src.models.allocation import (
    AllocationResponse,
    ConfidenceInterval,
    VariantAllocation,
    VariantMetrics,
)
from src.logging_config import log_algorithm

# Algorithm version - increment when logic changes
ALGORITHM_VERSION = "1.0.0"

# Z-score for 95% confidence interval
Z_95 = 1.96


def wilson_score_interval(clicks: int, impressions: int) -> Optional[ConfidenceInterval]:
    """
    Calculate Wilson Score confidence interval for CTR.
    
    More accurate than Wald interval for proportions, especially
    when the proportion is close to 0 or 1, or when sample size is small.
    
    Formula:
        center = (p + z²/2n) / (1 + z²/n)
        margin = z × √(p(1-p)/n + z²/4n²) / (1 + z²/n)
        lower = center - margin
        upper = center + margin
    
    Args:
        clicks: Number of successes (clicks)
        impressions: Number of trials (impressions)
        
    Returns:
        ConfidenceInterval or None if impressions is 0
    """
    if impressions == 0:
        return None
    
    n = impressions
    p = clicks / n
    z = Z_95
    z2 = z * z
    
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    margin = (z / denominator) * math.sqrt((p * (1 - p) / n) + (z2 / (4 * n * n)))
    
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    
    return ConfidenceInterval(
        lower=round(lower, 6),
        upper=round(upper, 6),
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


def generate_deterministic_seed(experiment_id: str, target_date: date) -> int:
    """
    Generate a deterministic seed based on experiment and date.
    
    Same experiment + same date = same seed = same results.
    Different date = different seed = allocation can evolve.
    
    Args:
        experiment_id: Experiment UUID
        target_date: Date for the seed
        
    Returns:
        Integer seed for numpy random
    """
    seed_str = f"{experiment_id}_{target_date.isoformat()}"
    seed_hash = hashlib.sha256(seed_str.encode()).hexdigest()
    return int(seed_hash, 16) % (2**32)


class ThompsonSamplingEngine:
    """
    Calculadora
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

    def calculate_allocation(
        self,
        variants: list[VariantData],
        seed: int | None = None,
    ) -> dict[str, float]:
        """
        Calculate traffic allocation using Thompson Sampling.
        
        For each Monte Carlo simulation:
        1. Sample θ from Beta(alpha, beta) for each variant
        2. The variant with highest θ "wins"
        3. Allocation = proportion of wins for each variant
        
        Args:
            variants: List of variant data with beta parameters
            seed: Random seed for reproducibility (optional)
            
        Returns:
            Dict mapping variant_name to allocation percentage
        """
        if not variants:
            return {}

        # Set seed for reproducibility
        if seed is not None:
            np.random.seed(seed)

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

        # Count wins for each variant (dicionário para as vitórias)
        wins = {v.variant_name: 0 for v in variants}

        # loop que roda 10K monte Carlo 
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
    """Orquestra o processo: busca usa e anota
    Service for computing traffic allocations."""

    def __init__(self):
        self.engine = ThompsonSamplingEngine()
        self.min_impressions = settings.min_impressions
        self.default_window = settings.default_window_days
        self.max_window = settings.max_window_days

    def get_allocation(
        self,
        experiment_id: str,
        window_days: int | None = None,
        save_history: bool = True,
    ) -> Optional[AllocationResponse]:
        """
        Get optimized traffic allocation for an experiment.
        
        Logic:
        1. Collect metrics from last `window_days` days (default 14)
        2. If any variant has < MIN_IMPRESSIONS, expand window to max (30 days)
        3. If still < MIN_IMPRESSIONS, use fallback (prior only)
        4. Use deterministic seed for reproducibility
        5. Save result to allocation_history
        
        Args:
            experiment_id: Experiment UUID
            window_days: Number of days to look back (default: 14)
            save_history: Whether to save to allocation_history (default: True)
            
        Returns:
            Allocation response or None if experiment not found
        """
        start_time = time.time()
        computed_at = datetime.utcnow()
        
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

        # Generate deterministic seed
        seed = generate_deterministic_seed(experiment_id, computed_at.date())

        # Calculate allocation with seed
        allocations = self.engine.calculate_allocation(variants, seed=seed)

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
                        ctr_ci=wilson_score_interval(v.clicks, v.impressions),
                    ),
                )
            )

        # Sort: control first, then by allocation descending
        variant_allocations.sort(
            key=lambda x: (-x.is_control, -x.allocation_percentage)
        )

        # Build algorithm description
        algorithm_name = "thompson_sampling"
        algorithm_desc = algorithm_name
        if used_fallback:
            algorithm_desc += " (fallback: prior only)"

        # Save to history
        if save_history:
            try:
                # Build variant data with CI
                variants_for_history = []
                for v in variants:
                    ci = wilson_score_interval(v.clicks, v.impressions)
                    variants_for_history.append({
                        "variant_id": v.variant_id,
                        "variant_name": v.variant_name,
                        "is_control": v.is_control,
                        "allocation_percentage": allocations.get(v.variant_name, 0.0),
                        "impressions": v.impressions,
                        "clicks": v.clicks,
                        "ctr": v.ctr,
                        "ctr_ci_lower": ci.lower if ci else None,
                        "ctr_ci_upper": ci.upper if ci else None,
                        "beta_alpha": v.beta_alpha,
                        "beta_beta": v.beta_beta,
                    })
                
                AllocationHistoryRepository.save_allocation(
                    experiment_id=experiment_id,
                    computed_at=computed_at,
                    window_days=actual_window,
                    algorithm=algorithm_name,
                    algorithm_version=ALGORITHM_VERSION,
                    seed=seed,
                    used_fallback=used_fallback,
                    variants=variants_for_history,
                )
            except Exception as e:
                # Log but don't fail the request if history save fails
                from src.logging_config import log_error
                log_error(
                    message=f"Failed to save allocation history: {e}",
                    error_type="allocation_history_save",
                    experiment_id=experiment_id,
                )

        # Log algorithm execution
        duration_ms = (time.time() - start_time) * 1000
        log_algorithm(
            algorithm=algorithm_name,
            experiment_id=experiment_id,
            duration_ms=duration_ms,
            n_samples=self.engine.n_samples,
            num_variants=len(variants),
            total_impressions=sum(v.impressions for v in variants),
            window_days=actual_window,
            used_fallback=used_fallback,
            seed=seed,
            algorithm_version=ALGORITHM_VERSION,
        )

        return AllocationResponse(
            experiment_id=experiment_id,
            experiment_name=experiment["name"],
            computed_at=computed_at,
            algorithm=algorithm_desc,
            window_days=actual_window,
            allocations=variant_allocations,
        )
