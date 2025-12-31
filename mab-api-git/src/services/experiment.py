"""Business logic for experiment operations."""

from datetime import date
from typing import Optional

from src.repositories.experiment import ExperimentRepository
from src.repositories.metrics import MetricsRepository
from src.models.experiment import ExperimentCreate, ExperimentResponse, VariantResponse
from src.models.metrics import MetricsBatchRequest, MetricsResponse


class ExperimentService:
    """Service for experiment business logic."""

    @staticmethod
    def create_experiment(data: ExperimentCreate) -> ExperimentResponse:
        """
        Create a new experiment with variants.
        
        Args:
            data: Experiment creation data
            
        Returns:
            Created experiment response
            
        Raises:
            ValueError: If experiment name already exists
        """
        # Check if name already exists
        existing = ExperimentRepository.get_experiment_by_name(data.name)
        if existing:
            raise ValueError(f"Experiment with name '{data.name}' already exists")

        # Create experiment
        variants = [{"name": v.name, "is_control": v.is_control} for v in data.variants]
        result = ExperimentRepository.create_experiment(
            name=data.name,
            description=data.description,
            variants=variants,
            optimization_target=data.optimization_target.value,
        )

        return ExperimentResponse(
            id=result["id"],
            name=result["name"],
            description=result["description"],
            status=result["status"],
            optimization_target=result["optimization_target"],
            variants=[
                VariantResponse(
                    id=v["id"],
                    name=v["name"],
                    is_control=v["is_control"],
                    created_at=v["created_at"],
                )
                for v in result["variants"]
            ],
            created_at=result["created_at"],
            updated_at=result["updated_at"],
        )

    @staticmethod
    def get_experiment(experiment_id: str) -> Optional[ExperimentResponse]:
        """
        Get experiment by ID.
        
        Args:
            experiment_id: Experiment UUID
            
        Returns:
            Experiment response or None if not found
        """
        result = ExperimentRepository.get_experiment_by_id(experiment_id)
        if not result:
            return None

        return ExperimentResponse(
            id=result["id"],
            name=result["name"],
            description=result["description"],
            status=result["status"],
            optimization_target=result.get("optimization_target", "ctr"),
            variants=[
                VariantResponse(
                    id=v["id"],
                    name=v["name"],
                    is_control=v["is_control"],
                    created_at=v["created_at"],
                )
                for v in result["variants"]
            ],
            created_at=result["created_at"],
            updated_at=result["updated_at"],
        )

    @staticmethod
    def record_metrics(
        experiment_id: str,
        data: MetricsBatchRequest,
    ) -> MetricsResponse:
        """
        Record metrics for an experiment's variants.
        
        Args:
            experiment_id: Experiment UUID
            data: Batch metrics data
            
        Returns:
            Metrics recording response
            
        Raises:
            ValueError: If experiment not found or variant not found
        """
        # Verify experiment exists
        experiment = ExperimentRepository.get_experiment_by_id(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        # Get variant map
        variants = {v["name"]: v["id"] for v in experiment["variants"]}

        # Validate all variant names exist
        for metric in data.metrics:
            if metric.variant_name not in variants:
                raise ValueError(
                    f"Variant '{metric.variant_name}' not found in experiment"
                )

        # Insert metrics
        for metric in data.metrics:
            variant_id = variants[metric.variant_name]
            MetricsRepository.insert_metrics(
                variant_id=variant_id,
                metric_date=data.date,
                impressions=metric.impressions,
                clicks=metric.clicks,
                sessions=metric.sessions,
                revenue=metric.revenue,
                source=data.source,
                batch_id=data.batch_id,
            )

        return MetricsResponse(
            message="Metrics recorded successfully",
            date=data.date,
            variants_updated=len(data.metrics),
            batch_id=data.batch_id,
        )
