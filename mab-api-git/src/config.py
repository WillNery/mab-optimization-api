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
    
    # Prior configuration (Beta distribution)
    # Prior esperado ~1% CTR: alpha=1, beta=99 → E[CTR] = 1/(1+99) = 0.01
    prior_alpha: int = 1
    prior_beta: int = 99

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
