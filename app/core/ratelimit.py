"""Shared rate limiter.

Lives outside main.py so routers can apply limits without importing the app
and creating a circular import.
"""

import time

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def login_key(request) -> str:
    """Throttle per client IP. Behind a proxy this needs X-Forwarded-For handling."""
    return get_remote_address(request)


limiter = Limiter(
    key_func=login_key,
    default_limits=[],
    enabled=settings.RATE_LIMIT_ENABLED,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
)


class FailedLoginTracker:
    """Consecutive failed logins per email address.

    The per-IP limit does nothing against a spread-out attack: ten tries from
    each of a thousand hosts is ten thousand tries at one account. This counts
    per address instead and stops answering for a while.

    Keyed on the *submitted* address whether or not it exists, and the caller
    answers a locked address exactly as it answers a wrong password — the
    lockout must not become the account-enumeration oracle the identical login
    message exists to prevent.

    In-process, like the limiter itself, and with the same limitation: a second
    instance keeps its own counters.
    """

    def __init__(self, threshold: int, lock_seconds: int) -> None:
        self.threshold = threshold
        self.lock_seconds = lock_seconds
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def is_locked(self, email: str) -> bool:
        until = self._locked_until.get(email)
        if until is None:
            return False
        if time.monotonic() >= until:
            self.reset(email)
            return False
        return True

    def record_failure(self, email: str) -> None:
        count = self._failures.get(email, 0) + 1
        self._failures[email] = count
        if count >= self.threshold:
            self._locked_until[email] = time.monotonic() + self.lock_seconds

    def reset(self, email: str) -> None:
        self._failures.pop(email, None)
        self._locked_until.pop(email, None)

    def clear(self) -> None:
        self._failures.clear()
        self._locked_until.clear()


failed_logins = FailedLoginTracker(
    threshold=settings.ACCOUNT_LOCK_AFTER_FAILURES,
    lock_seconds=settings.ACCOUNT_LOCK_MINUTES * 60,
)
