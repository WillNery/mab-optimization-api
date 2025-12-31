"""Repository for allocation history operations."""

import uuid
from datetime import datetime, date
from typing import Optional

from src.repositories.database import execute_query, get_connection
from src.sql import AllocationHistoryQueries


class AllocationHistoryRepository:
    """Repository for allocation history CRUD operations."""

    @staticmethod
    def save_allocation(
        experiment_id: str,
        computed_at: datetime,
        window_days: int,
        algorithm: str,
        algorithm_version: str,
        seed: int,
        used_fallback: bool,
        variants: list[dict],
    ) -> str:
        """
        Save allocation result to history.
        
        Args:
            experiment_id: Experiment UUID
            computed_at: When the allocation was computed
            window_days: Window used for calculation
            algorithm: Algorithm name
            algorithm_version: Algorithm version
            seed: Random seed used
            used_fallback: Whether fallback was used
            variants: List of variant allocation details
            
        Returns:
            Allocation history ID
        """
        history_id = str(uuid.uuid4())
        
        total_impressions = sum(v["impressions"] for v in variants)
        total_clicks = sum(v["clicks"] for v in variants)

        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Insert history record
                cursor.execute(
                    AllocationHistoryQueries.INSERT_HISTORY,
                    {
                        "id": history_id,
                        "experiment_id": experiment_id,
                        "computed_at": computed_at,
                        "window_days": window_days,
                        "algorithm": algorithm,
                        "algorithm_version": algorithm_version,
                        "seed": seed,
                        "used_fallback": used_fallback,
                        "total_impressions": total_impressions,
                        "total_clicks": total_clicks,
                    },
                )

                # Insert variant details
                for variant in variants:
                    detail_id = str(uuid.uuid4())
                    cursor.execute(
                        AllocationHistoryQueries.INSERT_DETAIL,
                        {
                            "id": detail_id,
                            "allocation_history_id": history_id,
                            "variant_id": variant["variant_id"],
                            "variant_name": variant["variant_name"],
                            "is_control": variant["is_control"],
                            "allocation_percentage": variant["allocation_percentage"],
                            "impressions": variant["impressions"],
                            "clicks": variant["clicks"],
                            "ctr": variant["ctr"],
                            "beta_alpha": variant["beta_alpha"],
                            "beta_beta": variant["beta_beta"],
                        },
                    )

                conn.commit()
                return history_id

            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()

    @staticmethod
    def get_history_by_experiment(
        experiment_id: str,
        limit: int = 30,
    ) -> list[dict]:
        """
        Get allocation history for an experiment.
        
        Args:
            experiment_id: Experiment UUID
            limit: Max number of records to return
            
        Returns:
            List of allocation history records
        """
        results = execute_query(
            AllocationHistoryQueries.SELECT_BY_EXPERIMENT,
            {"experiment_id": experiment_id, "limit": limit},
        )
        
        # Enrich with details
        for record in results:
            details = execute_query(
                AllocationHistoryQueries.SELECT_DETAILS_BY_HISTORY,
                {"allocation_history_id": record["id"]},
            )
            record["allocations"] = details
        
        return results

    @staticmethod
    def get_allocation_by_date(
        experiment_id: str,
        target_date: date,
    ) -> Optional[dict]:
        """
        Get allocation for a specific date.
        
        Args:
            experiment_id: Experiment UUID
            target_date: Date to look up
            
        Returns:
            Allocation record or None
        """
        results = execute_query(
            AllocationHistoryQueries.SELECT_BY_DATE,
            {"experiment_id": experiment_id, "target_date": target_date},
        )
        
        if not results:
            return None
        
        record = results[0]
        
        # Get details
        details = execute_query(
            AllocationHistoryQueries.SELECT_DETAILS_BY_HISTORY,
            {"allocation_history_id": record["id"]},
        )
        record["allocations"] = details
        
        return record
