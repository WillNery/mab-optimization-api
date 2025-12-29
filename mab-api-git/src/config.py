"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Snowflake connection
    snowflake_account: str
    snowflake_user: str
    snowflake_password: str
    snowflake_warehouse: str
    snowflake_database: str = "activeview_mab"
    snowflake_schema: str = "experiments"

    # API configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Algorithm configuration
    default_window_days: int = 14
    max_window_days: int = 30
    min_impressions: int = 200
    thompson_samples: int = 10000
    prior_alpha: int = 1
    prior_beta: int = 99

    # Logging configuration
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # Rate limiting configuration
    rate_limit_enabled: bool = True
    rate_limit_default_max: int = 100  # requests per window
    rate_limit_default_window: int = 60  # seconds

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
