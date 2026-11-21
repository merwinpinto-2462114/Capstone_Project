"""
EXAMFLOW – Application Configuration
Loaded from environment variables / .env file.
All secrets are injected at runtime from Google Cloud Secret Manager in production.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    APP_NAME: str = "EXAMFLOW"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # development | staging | production

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    DATABASE_URL: str  # e.g. postgresql+asyncpg://user:pass@host/db
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_ECHO: bool = False

    # ------------------------------------------------------------------ #
    # Security
    # ------------------------------------------------------------------ #
    SECRET_KEY: str                # Min 32 chars random hex; from Secret Manager in prod
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # ------------------------------------------------------------------ #
    # Pagination
    # ------------------------------------------------------------------ #
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 500

    # ------------------------------------------------------------------ #
    # Evaluation engine
    # ------------------------------------------------------------------ #
    # Minimum attempt percentage (inclusive boundary – see Rule 8)
    MIN_ATTEMPT_PERCENTAGE: float = 10.0

    # Normalisation: minimum shift size before pooling
    NORMALISATION_MIN_SHIFT_SIZE: int = 100

    # ------------------------------------------------------------------ #
    # Cloud
    # ------------------------------------------------------------------ #
    GCP_PROJECT_ID: Optional[str] = None
    CLOUD_SQL_INSTANCE: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    LOG_LEVEL: str = "INFO"
    USE_CLOUD_LOGGING: bool = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
