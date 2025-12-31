"""Repository for experiment data access."""

import uuid
from typing import Optional
from datetime import datetime

from src.repositories.database import execute_query, execute_write
from src.sql import ExperimentQueries, VariantQueries


class ExperimentRepository:
    """Repository for experiment database operations."""

    @staticmethod
    def create_experiment(
        name: str,
        description: Optional[str],
        variants: list[dict],
    ) -> dict:
        """
        Create a new experiment with its variants.
        
        Args:
            name: Experiment name
            description: Experiment description
            variants: List of variant dicts with 'name' and 'is_control'
            
        Returns:
            Created experiment dict with variants
        """
        experiment_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        # Insert experiment
        execute_write(
            ExperimentQueries.INSERT,
            {
                "id": experiment_id,
                "name": name,
                "description": description,
                "status": "active",
            },
            query_name="insert_experiment",
        )
        
        # Insert variants
        created_variants = []
        for variant in variants:
            variant_id = str(uuid.uuid4())
            execute_write(
                VariantQueries.INSERT,
                {
                    "id": variant_id,
                    "experiment_id": experiment_id,
                    "name": variant["name"],
                    "is_control": variant["is_control"],
                },
                query_name="insert_variant",
            )
            created_variants.append({
                "id": variant_id,
                "name": variant["name"],
                "is_control": variant["is_control"],
                "created_at": now,
            })
        
        return {
            "id": experiment_id,
            "name": name,
            "description": description,
            "status": "active",
            "variants": created_variants,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def get_experiment_by_id(experiment_id: str) -> Optional[dict]:
        """Get experiment by ID with its variants."""
        result = execute_query(
            ExperimentQueries.SELECT_BY_ID,
            {"id": experiment_id},
            query_name="get_experiment_by_id",
        )
        if not result:
            return None
        
        experiment = result[0]
        
        # Get variants
        variants = execute_query(
            VariantQueries.SELECT_BY_EXPERIMENT,
            {"experiment_id": experiment_id},
            query_name="get_variants_by_experiment",
        )
        
        experiment["variants"] = variants
        return experiment

    @staticmethod
    def get_experiment_by_name(name: str) -> Optional[dict]:
        """Get experiment by name."""
        result = execute_query(
            ExperimentQueries.SELECT_BY_NAME,
            {"name": name},
            query_name="get_experiment_by_name",
        )
        return result[0] if result else None

    @staticmethod
    def update_status(experiment_id: str, status: str) -> bool:
        """
        Update experiment status.
        
        Returns:
            True if updated, False if not found
        """
        rows_affected = execute_write(
            ExperimentQueries.UPDATE_STATUS,
            {"id": experiment_id, "status": status},
            query_name="update_experiment_status",
        )
        return rows_affected > 0


class VariantRepository:
    """Repository for variant database operations."""

    @staticmethod
    def create_variant(variant_data: dict) -> None:
        """Insert a new variant."""
        execute_write(
            VariantQueries.INSERT,
            variant_data,
            query_name="insert_variant",
        )

    @staticmethod
    def get_variants_by_experiment(experiment_id: str) -> list[dict]:
        """Get all variants for an experiment."""
        return execute_query(
            VariantQueries.SELECT_BY_EXPERIMENT,
            {"experiment_id": experiment_id},
            query_name="get_variants_by_experiment",
        )

    @staticmethod
    def get_variant_by_name_and_experiment(
        experiment_id: str, name: str
    ) -> Optional[dict]:
        """Get a specific variant by name within an experiment."""
        result = execute_query(
            VariantQueries.SELECT_BY_NAME_AND_EXPERIMENT,
            {"experiment_id": experiment_id, "name": name},
            query_name="get_variant_by_name",
        )
        return result[0] if result else None
