"""Application configuration, loaded from environment / .env file."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- application ---
    APP_NAME: str = "Grand Aurora Hotel"
    APP_ENV: Literal["development", "production", "test"] = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # --- database ---
    # SQLite (zero-setup, default) or PostgreSQL:
    #   postgresql+asyncpg://user:password@localhost:5432/hotel_db
    DATABASE_URL: str = "sqlite+aiosqlite:///./hotel.db"
    DB_ECHO: bool = False

    # --- security ---
    SECRET_KEY: str = "change-me-in-production-please-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    SESSION_COOKIE_NAME: str = "hotel_access_token"

    # --- cors ---
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # --- business rules ---
    CURRENCY: str = "AZN"
    CURRENCY_SYMBOL: str = "₼"
    TAX_RATE: float = 0.18  # VAT applied to invoices
    CHECK_IN_HOUR: int = 14
    CHECK_OUT_HOUR: int = 12

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
