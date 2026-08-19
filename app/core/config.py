"""Application configuration, loaded from environment / .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Secrets that ship with the repository. Safe for local work, never for production.
PUBLISHED_SECRET_KEYS = {
    "change-me-in-production-please-use-a-long-random-string",
    "compose-dev-secret-change-me-before-production",
}

MIN_SECRET_KEY_LENGTH = 32


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

    # --- rate limiting ---
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT: str = "10/minute"
    PASSWORD_CHANGE_RATE_LIMIT: str = "5/minute"
    #: Where the limiter keeps its counters. In-memory is per-process, so with
    #: more than one worker or container each keeps its own and the effective
    #: limit is multiplied by their number — point this at Redis
    #: ("redis://host:6379/0") as soon as there is a second instance.
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    #: Per-account brake, on top of the per-IP limit above: the IP limit alone
    #: does not stop a botnet spreading ten attempts per address over many
    #: hosts against one account.
    ACCOUNT_LOCK_AFTER_FAILURES: int = 10
    ACCOUNT_LOCK_MINUTES: int = 15

    # --- cors / hosts ---
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    #: Host header allow-list. Comma separated; "*" disables the check.
    TRUSTED_HOSTS: str = "*"

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
    def trusted_host_list(self) -> list[str]:
        return [h.strip() for h in self.TRUSTED_HOSTS.split(",") if h.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def docs_enabled(self) -> bool:
        """The schema names every endpoint — not something to publish in production."""
        return not self.is_production

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> "Settings":
        """Fail at boot rather than serve production traffic with dev defaults.

        Each of these is silent in a running app — a placeholder signing key
        forges sessions, `*` with credentialed CORS hands any origin the
        cookie. Crashing on start is the only reliable way to surface them.
        """
        if not self.is_production:
            return self

        problems: list[str] = []
        if self.SECRET_KEY in PUBLISHED_SECRET_KEYS:
            problems.append(
                "SECRET_KEY is still a value published in this repository — "
                'generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        elif len(self.SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
            problems.append(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters"
            )
        if self.DEBUG:
            problems.append("DEBUG must be false in production")
        if "*" in self.cors_origin_list:
            problems.append(
                "CORS_ORIGINS cannot be '*' because the session cookie is credentialed"
            )
        if "*" in self.trusted_host_list:
            problems.append(
                "TRUSTED_HOSTS cannot be '*' in production — it disables the Host "
                "header check entirely. Set the real hostnames, comma separated."
            )
        if problems:
            raise ValueError(
                "Refusing to start with APP_ENV=production:\n  - " + "\n  - ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
