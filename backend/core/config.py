"""Core configuration with Pydantic v2 Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    app_env: str = "development"
    database_url: str = "postgresql://user:password@localhost/dbname"
    log_level: str = "INFO"


# Global settings instance
settings = Settings()
