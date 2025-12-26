"""Unit tests for Thompson Sampling allocation."""

import pytest
from src.services.allocation import ThompsonSamplingEngine, VariantData


class TestThompsonSamplingEngine:
    """Tests for Thompson Sampling algorithm."""

    def setup_method(self):
        """Set up test engine with fixed seed for reproducibility."""
        self.engine = ThompsonSamplingEngine(n_samples=10000)

    def test_allocation_with_clear_winner(self):
        """Variant with much higher CTR should get majority of allocation."""
        variants = [
            VariantData(
                variant_id="var_001",
                variant_name="control",
                is_control=True,
                impressions=10000,
                clicks=100,  # 1% CTR
                ctr=0.01,
                beta_alpha=101,
                beta_beta=9901,
            ),
            VariantData(
                variant_id="var_002",
                variant_name="variant_a",
                is_control=False,
                impressions=10000,
                clicks=500,  # 5% CTR - much better
                ctr=0.05,
                beta_alpha=501,
                beta_beta=9501,
            ),
        ]

        allocations = self.engine.calculate_allocation(variants)

        # variant_a should get significantly more traffic
        assert allocations["variant_a"] > allocations["control"]
        assert allocations["variant_a"] > 90  # Should be dominant
        assert sum(allocations.values()) == pytest.approx(100, abs=0.1)

    def test_allocation_with_equal_performance(self):
        """Equal performers should get roughly equal allocation."""
        variants = [
            VariantData(
                variant_id="var_001",
                variant_name="control",
                is_control=True,
                impressions=10000,
                clicks=300,
                ctr=0.03,
                beta_alpha=301,
                beta_beta=9701,
            ),
            VariantData(
                variant_id="var_002",
                variant_name="variant_a",
                is_control=False,
                impressions=10000,
                clicks=300,
                ctr=0.03,
                beta_alpha=301,
                beta_beta=9701,
            ),
        ]

        allocations = self.engine.calculate_allocation(variants)

        # Should be roughly 50/50
        assert 40 < allocations["control"] < 60
        assert 40 < allocations["variant_a"] < 60
        assert sum(allocations.values()) == pytest.approx(100, abs=0.1)

    def test_allocation_with_no_data(self):
        """No data should result in uniform allocation."""
        variants = [
            VariantData(
                variant_id="var_001",
                variant_name="control",
                is_control=True,
                impressions=0,
                clicks=0,
                ctr=0,
                beta_alpha=1,
                beta_beta=1,
            ),
            VariantData(
                variant_id="var_002",
                variant_name="variant_a",
                is_control=False,
                impressions=0,
                clicks=0,
                ctr=0,
                beta_alpha=1,
                beta_beta=1,
            ),
        ]

        allocations = self.engine.calculate_allocation(variants)

        # Should be uniform (50% each)
        assert allocations["control"] == 50.0
        assert allocations["variant_a"] == 50.0

    def test_allocation_with_three_variants(self):
        """Should work with more than 2 variants (multi-armed bandit)."""
        variants = [
            VariantData(
                variant_id="var_001",
                variant_name="control",
                is_control=True,
                impressions=10000,
                clicks=200,  # 2% CTR
                ctr=0.02,
                beta_alpha=201,
                beta_beta=9801,
            ),
            VariantData(
                variant_id="var_002",
                variant_name="variant_a",
                is_control=False,
                impressions=10000,
                clicks=400,  # 4% CTR
                ctr=0.04,
                beta_alpha=401,
                beta_beta=9601,
            ),
            VariantData(
                variant_id="var_003",
                variant_name="variant_b",
                is_control=False,
                impressions=10000,
                clicks=300,  # 3% CTR
                ctr=0.03,
                beta_alpha=301,
                beta_beta=9701,
            ),
        ]

        allocations = self.engine.calculate_allocation(variants)

        # variant_a (best) > variant_b > control
        assert allocations["variant_a"] > allocations["variant_b"]
        assert allocations["variant_b"] > allocations["control"]
        assert sum(allocations.values()) == pytest.approx(100, abs=0.1)

    def test_allocation_empty_variants(self):
        """Empty variant list should return empty allocation."""
        allocations = self.engine.calculate_allocation([])
        assert allocations == {}

    def test_beta_parameters_calculation(self):
        """Verify beta parameters are correctly used."""
        # Beta(101, 9901) = 100 clicks, 10000 impressions
        variant = VariantData(
            variant_id="var_001",
            variant_name="test",
            is_control=True,
            impressions=10000,
            clicks=100,
            ctr=0.01,
            beta_alpha=101,  # clicks + 1
            beta_beta=9901,  # impressions - clicks + 1
        )
        
        # Verify the formula
        assert variant.beta_alpha == variant.clicks + 1
        assert variant.beta_beta == variant.impressions - variant.clicks + 1

    def test_allocation_sums_to_100(self, sample_variant_data):
        """Allocations should always sum to 100%."""
        allocations = self.engine.calculate_allocation(sample_variant_data)
        
        total = sum(allocations.values())
        assert total == pytest.approx(100, abs=0.1)


class TestValidation:
    """Tests for input validation."""

    def test_clicks_cannot_exceed_impressions(self):
        """Clicks > impressions should raise validation error."""
        from src.models.metrics import MetricInput
        
        with pytest.raises(ValueError, match="cannot exceed"):
            MetricInput(
                variant_name="test",
                impressions=100,
                clicks=150,  # More clicks than impressions
            )

    def test_experiment_requires_control(self):
        """Experiment without control variant should raise error."""
        from src.models.experiment import ExperimentCreate
        
        with pytest.raises(ValueError, match="control"):
            ExperimentCreate(
                name="test",
                variants=[
                    {"name": "variant_a", "is_control": False},
                    {"name": "variant_b", "is_control": False},
                ],
            )

    def test_experiment_requires_unique_variant_names(self):
        """Duplicate variant names should raise error."""
        from src.models.experiment import ExperimentCreate
        
        with pytest.raises(ValueError, match="unique"):
            ExperimentCreate(
                name="test",
                variants=[
                    {"name": "control", "is_control": True},
                    {"name": "control", "is_control": False},  # Duplicate
                ],
            )

    def test_experiment_requires_minimum_variants(self):
        """Experiment with less than 2 variants should raise error."""
        from src.models.experiment import ExperimentCreate
        
        with pytest.raises(ValueError):
            ExperimentCreate(
                name="test",
                variants=[
                    {"name": "control", "is_control": True},
                ],
            )
