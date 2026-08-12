"""Boot-time refusal to run production on development defaults.

Plain sync tests — these build Settings directly and never touch the app.
"""

import pytest

from app.core.config import Settings

SAFE_PRODUCTION = {
    "APP_ENV": "production",
    "DEBUG": False,
    "SECRET_KEY": "x" * 40,
    "CORS_ORIGINS": "https://hotel.example",
}


@pytest.mark.parametrize(
    "override",
    [
        {"SECRET_KEY": "change-me-in-production-please-use-a-long-random-string"},
        {"SECRET_KEY": "compose-dev-secret-change-me-before-production"},
        {"SECRET_KEY": "tooshort"},
        {"DEBUG": True},
        {"CORS_ORIGINS": "*"},
    ],
    ids=["shipped-key", "compose-key", "short-key", "debug-on", "cors-wildcard"],
)
def test_production_refuses_to_start_with_unsafe_settings(override):
    with pytest.raises(ValueError):
        Settings(**{**SAFE_PRODUCTION, **override})


def test_a_correctly_configured_production_still_starts():
    settings = Settings(**SAFE_PRODUCTION)
    assert settings.is_production
    assert not settings.docs_enabled, "the OpenAPI schema must not be public"


def test_development_keeps_the_docs_and_the_shipped_defaults():
    settings = Settings(APP_ENV="development")
    assert settings.docs_enabled
