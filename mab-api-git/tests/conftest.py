"""Test fixtures and configuration."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_experiment_data():
    """Sample experiment creation data."""
    return {
        "name": "test_experiment",
        "description": "Test experiment for unit tests",
        "variants": [
            {"name": "control", "is_control": True},
            {"name": "variant_a", "is_control": False},
        ],
    }


@pytest.fixture
def sample_metrics_data():
    """Sample metrics data."""
    return {
        "date": "2025-01-15",
        "metrics": [
            {"variant_name": "control", "impressions": 10000, "clicks": 320},
            {"variant_name": "variant_a", "impressions": 10000, "clicks": 450},
        ],
    }


@pytest.fixture
def sample_variant_data():
    """Sample variant data for Thompson Sampling tests."""
    from src.services.allocation import VariantData
    
    return [
        VariantData(
            variant_id="var_001",
            variant_name="control",
            is_control=True,
            impressions=10000,
            clicks=320,
            ctr=0.032,
            beta_alpha=321,
            beta_beta=9681,
        ),
        VariantData(
            variant_id="var_002",
            variant_name="variant_a",
            is_control=False,
            impressions=10000,
            clicks=450,
            ctr=0.045,
            beta_alpha=451,
            beta_beta=9551,
        ),
    ]


@pytest.fixture
def mock_snowflake():
    """Mock Snowflake connection."""
    with patch("src.repositories.database.get_connection") as mock:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock.return_value.__exit__ = MagicMock(return_value=False)
        yield mock
