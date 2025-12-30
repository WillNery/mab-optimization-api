"""Repository for experiment data access."""
from typing import Optional
from src.database.database import execute_query, execute_write
from src.sql.queries import ExperimentQueries, VariantQueries


class ExperimentRepository:
    """Repository for experiment database operations."""

    @staticmethod
    def create_experiment(experiment_data: dict) -> None:
        """Insert a new experiment."""
        execute_write(ExperimentQueries.INSERT, experiment_data)

    @staticmethod
    def get_experiment_by_id(experiment_id: str) -> Optional[dict]:
        """Get experiment by ID."""
        result = execute_query(ExperimentQueries.SELECT_BY_ID, {"id": experiment_id})
        return result[0] if result else None

    @staticmethod
    def get_experiment_by_name(name: str) -> Optional[dict]:
        """Get experiment by name."""
        result = execute_query(ExperimentQueries.SELECT_BY_NAME, {"name": name})
        return result[0] if result else None

    @staticmethod
    def update_status(experiment_id: str, status: str) -> None:
        """Update experiment status."""
        execute_write(
            ExperimentQueries.UPDATE_STATUS,
            {"id": experiment_id, "status": status}
        )


class VariantRepository:
    """Repository for variant database operations."""

    @staticmethod
    def create_variant(variant_data: dict) -> None:
        """Insert a new variant."""
        execute_write(VariantQueries.INSERT, variant_data)

    @staticmethod
    def get_variants_by_experiment(experiment_id: str) -> list[dict]:
        """Get all variants for an experiment."""
        return execute_query(
            VariantQueries.SELECT_BY_EXPERIMENT,
            {"experiment_id": experiment_id}
        )

    @staticmethod
    def get_variant_by_name_and_experiment(
        experiment_id: str, name: str
    ) -> Optional[dict]:
        """Get a specific variant by name within an experiment."""
        result = execute_query(
            VariantQueries.SELECT_BY_NAME_AND_EXPERIMENT,
            {"experiment_id": experiment_id, "name": name}
        )
        return result[0] if result else None
