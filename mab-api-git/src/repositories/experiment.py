"""Repository for experiment and variant operations."""

import uuid
from datetime import datetime
from typing import Optional

from src.repositories.database import execute_query, execute_write, get_connection
from src.sql import ExperimentQueries, VariantQueries


class ExperimentRepository:
    """Repository for experiment CRUD operations."""

    @staticmethod
    def create_experiment(
        name: str,
        description: Optional[str],
        optimization_target: str,
        variants: list[dict],
    ) -> dict:
        """
        Create a new experiment with its variants.
        
        Args:
            name: Experiment name
            description: Experiment description
            optimization_target: Metric to optimize (ctr, rps, rpm)
            variants: List of variant dicts with 'name' and 'is_control'
            
        Returns:
            Created experiment dict with variants
        """
        experiment_id = str(uuid.uuid4())
        now = datetime.utcnow()

        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Insert experiment
                cursor.execute(
                    ExperimentQueries.INSERT,
                    {
                        "id": experiment_id,
                        "name": name,
                        "description": description,
                        "status": "active",
                        "optimization_target": optimization_target,
                    },
                )

                # Insert variants
                created_variants = []
                for variant in variants:
                    variant_id = str(uuid.uuid4())
                    cursor.execute(
                        VariantQueries.INSERT,
                        {
                            "id": variant_id,
                            "experiment_id": experiment_id,
                            "name": variant["name"],
                            "is_control": variant["is_control"],
                        },
                    )
                    created_variants.append({
                        "id": variant_id,
                        "name": variant["name"],
                        "is_control": variant["is_control"],
                        "created_at": now,
                    })

                conn.commit()

                return {
                    "id": experiment_id,
                    "name": name,
                    "description": description,
                    "status": "active",
                    "optimization_target": optimization_target,
                    "variants": created_variants,
                    "created_at": now,
                    "updated_at": now,
                }
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()

    @staticmethod
    def get_experiment_by_id(experiment_id: str) -> Optional[dict]:
        """
        Get experiment by ID.
        
        Args:
            experiment_id: Experiment UUID
            
        Returns:
            Experiment dict or None if not found
        """
        results = execute_query(
            ExperimentQueries.SELECT_BY_ID,
            {"id": experiment_id},
        )
        if not results:
            return None

        experiment = results[0]
        
        # Get variants
        variants = execute_query(
            VariantQueries.SELECT_BY_EXPERIMENT,
            {"experiment_id": experiment_id},
        )
        experiment["variants"] = variants
        
        return experiment

    @staticmethod
    def get_experiment_by_name(name: str) -> Optional[dict]:
        """
        Get experiment by name.
        
        Args:
            name: Experiment name
            
        Returns:
            Experiment dict or None if not found
        """
        results = execute_query(
            ExperimentQueries.SELECT_BY_NAME,
            {"name": name},
        )
        if not results:
            return None

        experiment = results[0]
        
        # Get variants
        variants = execute_query(
            VariantQueries.SELECT_BY_EXPERIMENT,
            {"experiment_id": experiment["id"]},
        )
        experiment["variants"] = variants
        
        return experiment

    @staticmethod
    def get_variants_by_experiment(experiment_id: str) -> list[dict]:
        """
        Get all variants for an experiment.
        
        Args:
            experiment_id: Experiment UUID
            
        Returns:
            List of variant dicts
        """
        return execute_query(
            VariantQueries.SELECT_BY_EXPERIMENT,
            {"experiment_id": experiment_id},
        )

    @staticmethod
    def get_variant_by_name(experiment_id: str, variant_name: str) -> Optional[dict]:
        """
        Get variant by name within an experiment.
        
        Args:
            experiment_id: Experiment UUID
            variant_name: Variant name
            
        Returns:
            Variant dict or None if not found
        """
        results = execute_query(
            VariantQueries.SELECT_BY_NAME_AND_EXPERIMENT,
            {"experiment_id": experiment_id, "name": variant_name},
        )
        return results[0] if results else None
