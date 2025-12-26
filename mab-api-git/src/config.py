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
    thompson_samples: int = 10000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
