"""Repository for metrics operations."""

import uuid
from datetime import date
from decimal import Decimal

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
        sessions: int = 0,
        revenue: Decimal = Decimal("0"),
        source: str = "api",
        batch_id: str | None = None,
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
            sessions: Number of unique sessions
            revenue: Revenue in USD
            source: Origin of the data (api, gam, cdp, manual)
            batch_id: Batch ID for traceability
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
                        "sessions": sessions,
                        "impressions": impressions,
                        "clicks": clicks,
                        "revenue": float(revenue),
                        "source": source,
                        "batch_id": batch_id,
                    },
                )

                # Upsert into daily_metrics
                cursor.execute(
                    MetricsQueries.UPSERT_DAILY,
                    {
                        "id": daily_id,
                        "variant_id": variant_id,
                        "metric_date": metric_date,
                        "sessions": sessions,
                        "impressions": impressions,
                        "clicks": clicks,
                        "revenue": float(revenue),
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
                "prior_alpha": settings.prior_alpha,
                "prior_beta": settings.prior_beta,
            },
            query_name="get_metrics_for_allocation",
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
            query_name="get_metrics_history",
        )
