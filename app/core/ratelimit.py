"""Shared rate limiter.

Lives outside main.py so routers can apply limits without importing the app
and creating a circular import.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def login_key(request) -> str:
    """Throttle per client IP. Behind a proxy this needs X-Forwarded-For handling."""
    return get_remote_address(request)


limiter = Limiter(key_func=login_key, default_limits=[], enabled=settings.RATE_LIMIT_ENABLED)
