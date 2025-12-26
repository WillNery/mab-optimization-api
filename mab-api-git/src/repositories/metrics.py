"""Repository for metrics operations."""

import uuid
from datetime import date

from src.repositories.database import execute_query, get_connection
from src.sql import MetricsQueries
from src.config import settings


class MetricsRepository:
    """Repository for metrics CRUD operations."""

    @staticmethod
    def insert_metrics(
        variant_id: str,
        metric_date: date,
        impressions: int,
        clicks: int,
    ) -> None:
        """
        Insert metrics into both raw and daily tables.
        
        Raw table: append-only for audit
        Daily table: upsert for clean data
        
        Args:
            variant_id: Variant UUID
            metric_date: Date of the metrics
            impressions: Number of impressions
            clicks: Number of clicks
        """
        raw_id = str(uuid.uuid4())
        daily_id = str(uuid.uuid4())

        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Insert into raw_metrics (append-only)
                cursor.execute(
                    MetricsQueries.INSERT_RAW,
                    {
                        "id": raw_id,
                        "variant_id": variant_id,
                        "metric_date": metric_date,
                        "impressions": impressions,
                        "clicks": clicks,
                    },
                )

                # Upsert into daily_metrics
                cursor.execute(
                    MetricsQueries.UPSERT_DAILY,
                    {
                        "id": daily_id,
                        "variant_id": variant_id,
                        "metric_date": metric_date,
                        "impressions": impressions,
                        "clicks": clicks,
                    },
                )

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()

    @staticmethod
    def get_metrics_for_allocation(
        experiment_id: str,
        window_days: int | None = None,
    ) -> list[dict]:
        """
        Get aggregated metrics for Thompson Sampling calculation.
        
        Args:
            experiment_id: Experiment UUID
            window_days: Number of days to look back (default from settings)
            
        Returns:
            List of dicts with variant metrics and beta parameters
        """
        if window_days is None:
            window_days = settings.default_window_days

        return execute_query(
            MetricsQueries.SELECT_FOR_ALLOCATION,
            {
                "experiment_id": experiment_id,
                "window_days": window_days,
            },
        )

    @staticmethod
    def get_metrics_history(experiment_id: str) -> list[dict]:
        """
        Get historical metrics for an experiment.
        
        Args:
            experiment_id: Experiment UUID
            
        Returns:
            List of daily metrics per variant
        """
        return execute_query(
            MetricsQueries.SELECT_HISTORY,
            {"experiment_id": experiment_id},
        )
