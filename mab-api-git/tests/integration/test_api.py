"""Integration tests for API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


def utc_now():
    """Helper para criar datetime UTC sem deprecation warning."""
    return datetime.now(timezone.utc)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestExperimentEndpoints:
    """Tests for experiment endpoints."""

    @patch("src.services.experiment.ExperimentRepository")
    def test_create_experiment_success(self, mock_repo, client, sample_experiment_data):
        """Should create experiment successfully."""
        mock_repo.get_experiment_by_name.return_value = None
        mock_repo.create_experiment.return_value = {
            "id": "exp_123",
            "name": sample_experiment_data["name"],
            "description": sample_experiment_data["description"],
            "status": "active",
            "optimization_target": "ctr",
            "variants": [
                {"id": "var_001", "name": "control", "is_control": True, "created_at": utc_now()},
                {"id": "var_002", "name": "variant_a", "is_control": False, "created_at": utc_now()},
            ],
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        response = client.post("/experiments", json=sample_experiment_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_experiment_data["name"]
        assert len(data["variants"]) == 2

    @patch("src.services.experiment.ExperimentRepository")
    def test_create_experiment_duplicate_name(self, mock_repo, client, sample_experiment_data):
        """Should return 409 for duplicate experiment name."""
        mock_repo.get_experiment_by_name.return_value = {"id": "existing"}

        response = client.post("/experiments", json=sample_experiment_data)

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_experiment_no_control(self, client):
        """Should return 422 for experiment without control variant."""
        data = {
            "name": "test",
            "variants": [
                {"name": "variant_a", "is_control": False},
                {"name": "variant_b", "is_control": False},
            ],
        }

        response = client.post("/experiments", json=data)

        assert response.status_code == 422

    def test_create_experiment_single_variant(self, client):
        """Should return 422 for experiment with only one variant."""
        data = {
            "name": "test",
            "variants": [
                {"name": "control", "is_control": True},
            ],
        }

        response = client.post("/experiments", json=data)

        assert response.status_code == 422

    @patch("src.services.experiment.ExperimentRepository")
    def test_get_experiment_success(self, mock_repo, client):
        """Should return experiment details."""
        mock_repo.get_experiment_by_id.return_value = {
            "id": "exp_123",
            "name": "test_experiment",
            "description": "Test",
            "status": "active",
            "optimization_target": "ctr",
            "variants": [
                {"id": "var_001", "name": "control", "is_control": True, "created_at": utc_now()},
            ],
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        response = client.get("/experiments/exp_123")

        assert response.status_code == 200
        assert response.json()["id"] == "exp_123"

    @patch("src.services.experiment.ExperimentRepository")
    def test_get_experiment_not_found(self, mock_repo, client):
        """Should return 404 for non-existent experiment."""
        mock_repo.get_experiment_by_id.return_value = None

        response = client.get("/experiments/nonexistent")

        assert response.status_code == 404


class TestMetricsEndpoints:
    """Tests for metrics endpoints."""

    @patch("src.services.experiment.MetricsRepository")
    @patch("src.services.experiment.ExperimentRepository")
    def test_record_metrics_success(
        self, mock_exp_repo, mock_metrics_repo, client, sample_metrics_data
    ):
        """Should record metrics successfully."""
        mock_exp_repo.get_experiment_by_id.return_value = {
            "id": "exp_123",
            "status": "active",
            "variants": [
                {"id": "var_001", "name": "control"},
                {"id": "var_002", "name": "variant_a"},
            ],
        }

        response = client.post("/experiments/exp_123/metrics", json=sample_metrics_data)

        assert response.status_code == 201
        data = response.json()
        assert data["variants_updated"] == 2

    @patch("src.services.experiment.ExperimentRepository")
    def test_record_metrics_experiment_not_found(
        self, mock_repo, client, sample_metrics_data
    ):
        """Should return 404 for non-existent experiment."""
        mock_repo.get_experiment_by_id.return_value = None

        response = client.post("/experiments/nonexistent/metrics", json=sample_metrics_data)

        assert response.status_code == 404

    @patch("src.services.experiment.MetricsRepository")
    @patch("src.services.experiment.ExperimentRepository")
    def test_record_metrics_invalid_variant(self, mock_exp_repo, mock_metrics_repo, client):
        """Should return 400 for non-existent variant."""
        mock_exp_repo.get_experiment_by_id.return_value = {
            "id": "exp_123",
            "status": "active",
            "variants": [
                {"id": "var_001", "name": "control"},
            ],
        }

        data = {
            "date": "2025-01-15",
            "metrics": [
                {"variant_name": "nonexistent", "impressions": 100, "clicks": 10},
            ],
        }

        response = client.post("/experiments/exp_123/metrics", json=data)

        assert response.status_code == 400
        assert "not found" in response.json()["detail"]

    def test_record_metrics_clicks_exceed_impressions(self, client):
        """Should return 422 when clicks > impressions."""
        data = {
            "date": "2025-01-15",
            "metrics": [
                {"variant_name": "control", "impressions": 100, "clicks": 150},
            ],
        }

        response = client.post("/experiments/exp_123/metrics", json=data)

        assert response.status_code == 422


class TestAllocationEndpoints:
    """Tests for allocation endpoints."""

    @patch("src.services.allocation.AllocationHistoryRepository")
    @patch("src.services.allocation.MetricsRepository")
    @patch("src.services.allocation.ExperimentRepository")
    @patch("src.routers.experiments.ExperimentService")
    def test_get_allocation_success(
        self, mock_service, mock_exp_repo, mock_metrics_repo, mock_history_repo, client
    ):
        """Should return allocation successfully."""
        # Mock para verificação de status no router
        mock_experiment = MagicMock()
        mock_experiment.status = "active"
        mock_service.get_experiment.return_value = mock_experiment
        
        # Mock para o repository usado pelo service
        mock_exp_repo.get_experiment_by_id.return_value = {
            "id": "exp_123",
            "name": "test_experiment",
            "status": "active",
        }
        mock_metrics_repo.get_metrics_for_allocation.return_value = [
            {
                "variant_id": "var_001",
                "variant_name": "control",
                "is_control": True,
                "impressions": 10000,
                "clicks": 320,
                "ctr": 0.032,
                "beta_alpha": 321,
                "beta_beta": 9779,
            },
            {
                "variant_id": "var_002",
                "variant_name": "variant_a",
                "is_control": False,
                "impressions": 10000,
                "clicks": 450,
                "ctr": 0.045,
                "beta_alpha": 451,
                "beta_beta": 9649,
            },
        ]
        mock_history_repo.save_allocation.return_value = "history_123"

        response = client.get("/experiments/exp_123/allocation")

        assert response.status_code == 200
        data = response.json()
        assert data["algorithm"] == "thompson_sampling"
        assert len(data["allocations"]) == 2
        
        # Check allocations sum to 100%
        total = sum(a["allocation_percentage"] for a in data["allocations"])
        assert abs(total - 100) < 0.2

    @patch("src.routers.experiments.ExperimentService")
    def test_get_allocation_not_found(self, mock_service, client):
        """Should return 404 for non-existent experiment."""
        mock_service.get_experiment.return_value = None

        response = client.get("/experiments/nonexistent/allocation")

        assert response.status_code == 404

    @patch("src.routers.experiments.ExperimentService")
    def test_get_allocation_experiment_not_active(self, mock_service, client):
        """Should return 400 for non-active experiment."""
        mock_experiment = MagicMock()
        mock_experiment.status = "paused"
        mock_service.get_experiment.return_value = mock_experiment

        response = client.get("/experiments/exp_123/allocation")

        assert response.status_code == 400
        assert "paused" in response.json()["detail"]

    @patch("src.services.allocation.AllocationHistoryRepository")
    @patch("src.services.allocation.MetricsRepository")
    @patch("src.services.allocation.ExperimentRepository")
    @patch("src.routers.experiments.ExperimentService")
    def test_get_allocation_with_window_days(
        self, mock_service, mock_exp_repo, mock_metrics_repo, mock_history_repo, client
    ):
        """Should accept custom window_days parameter."""
        mock_experiment = MagicMock()
        mock_experiment.status = "active"
        mock_service.get_experiment.return_value = mock_experiment
        
        mock_exp_repo.get_experiment_by_id.return_value = {
            "id": "exp_123",
            "name": "test_experiment",
            "status": "active",
        }
        mock_metrics_repo.get_metrics_for_allocation.return_value = [
            {
                "variant_id": "var_001",
                "variant_name": "control",
                "is_control": True,
                "impressions": 0,
                "clicks": 0,
                "ctr": 0,
                "beta_alpha": 1,
                "beta_beta": 99,
            },
        ]

        response = client.get("/experiments/exp_123/allocation?window_days=7")

        assert response.status_code == 200
        # Window might be expanded due to insufficient data
        assert response.json()["window_days"] >= 7

    @patch("src.services.allocation.AllocationHistoryRepository")
    @patch("src.services.allocation.MetricsRepository")
    @patch("src.services.allocation.ExperimentRepository")
    @patch("src.routers.experiments.ExperimentService")
    def test_get_allocation_no_data_uniform(
        self, mock_service, mock_exp_repo, mock_metrics_repo, mock_history_repo, client
    ):
        """Should return uniform allocation when no data."""
        mock_experiment = MagicMock()
        mock_experiment.status = "active"
        mock_service.get_experiment.return_value = mock_experiment
        
        mock_exp_repo.get_experiment_by_id.return_value = {
            "id": "exp_123",
            "name": "test_experiment",
            "status": "active",
        }
        mock_metrics_repo.get_metrics_for_allocation.return_value = [
            {
                "variant_id": "var_001",
                "variant_name": "control",
                "is_control": True,
                "impressions": 0,
                "clicks": 0,
                "ctr": 0,
                "beta_alpha": 1,
                "beta_beta": 99,
            },
            {
                "variant_id": "var_002",
                "variant_name": "variant_a",
                "is_control": False,
                "impressions": 0,
                "clicks": 0,
                "ctr": 0,
                "beta_alpha": 1,
                "beta_beta": 99,
            },
        ]

        response = client.get("/experiments/exp_123/allocation")

        assert response.status_code == 200
        allocations = response.json()["allocations"]
        
        # Should be uniform (50% each)
        for alloc in allocations:
            assert alloc["allocation_percentage"] == 50.0
