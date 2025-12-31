"""Repository for allocation history operations."""

import json
import uuid
from datetime import datetime

from src.repositories.database import execute_write
from src.sql import AllocationHistoryQueries


class AllocationHistoryRepository:
    """Repository for allocation history operations."""

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

        execute_write(
            AllocationHistoryQueries.INSERT,
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
                "allocations": json.dumps(variants),
            },
        )

        return history_id
