"""Shared rate limiter.

Lives outside main.py so routers can apply limits without importing the app
and creating a circular import.
"""

import time
from collections import OrderedDict

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


#: Most email addresses the tracker below will ever see are attacker-supplied
#: and will never be seen again, so the store has to be bounded. Comfortably
#: above the number of distinct staff addresses a hotel has.
MAX_TRACKED_ACCOUNTS = 4096

#: A failure that old is not part of a live attack, so it is not worth
#: remembering. Also the ceiling on how long an abandoned entry survives.
FAILURE_TTL_SECONDS = 3600


class FailedLoginTracker:
    """Consecutive failed logins per email address.

    The per-IP limit does nothing against a spread-out attack: ten tries from
    each of a thousand hosts is ten thousand tries at one account. This counts
    per address instead and stops answering for a while.

    Keyed on the *submitted* address whether or not it exists, and the caller
    answers a locked address exactly as it answers a wrong password — the
    lockout must not become the account-enumeration oracle the identical login
    message exists to prevent.

    **Bounded, because the key is chosen by the caller.** This was two plain
    dicts that only ever shed an entry on a successful login, so every distinct
    address an attacker submitted stayed for the lifetime of the process — the
    rate limit caps the rate, not the total, and ten a minute for a day is
    14,400 entries per source address. Entries now expire and the store is
    capped, evicting whatever was touched longest ago.

    In-process, like the limiter itself, and with the same limitation: a second
    instance keeps its own counters. Moving both to Redis is tracked in
    `SECURITY-TODO.md` — that fixes the sharing; this fixes the growth.
    """

    def __init__(
        self,
        threshold: int,
        lock_seconds: int,
        *,
        max_accounts: int = MAX_TRACKED_ACCOUNTS,
        ttl_seconds: int = FAILURE_TTL_SECONDS,
    ) -> None:
        self.threshold = threshold
        self.lock_seconds = lock_seconds
        self.max_accounts = max_accounts
        self.ttl_seconds = ttl_seconds
        # Insertion-ordered, so the oldest entry is the first key. Values are
        # (failure count, locked-until or None, last-touched).
        self._entries: OrderedDict[str, tuple[int, float | None, float]] = OrderedDict()

    def _expired(self, entry: tuple[int, float | None, float], now: float) -> bool:
        _count, locked_until, touched = entry
        if locked_until is not None and now < locked_until:
            return False  # an active lock never expires early
        return now - touched >= self.ttl_seconds

    def _evict(self, now: float) -> None:
        for email in [e for e, v in self._entries.items() if self._expired(v, now)]:
            del self._entries[email]
        # Still full: drop least-recently-touched first. An attacker can push a
        # real account out this way, which costs them their own lockout on it —
        # strictly better than the unbounded growth it replaces.
        while len(self._entries) >= self.max_accounts:
            self._entries.popitem(last=False)

    def is_locked(self, email: str) -> bool:
        entry = self._entries.get(email)
        if entry is None:
            return False
        _count, locked_until, _touched = entry
        if locked_until is None:
            return False
        if time.monotonic() >= locked_until:
            self.reset(email)
            return False
        return True

    def record_failure(self, email: str) -> None:
        now = time.monotonic()
        if email not in self._entries:
            self._evict(now)
        count = self._entries.get(email, (0, None, now))[0] + 1
        locked_until = now + self.lock_seconds if count >= self.threshold else None
        self._entries[email] = (count, locked_until, now)
        self._entries.move_to_end(email)

    def reset(self, email: str) -> None:
        self._entries.pop(email, None)

    def clear(self) -> None:
        self._entries.clear()

    @property
    def tracked(self) -> int:
        """How many addresses are held. Exposed so a test can pin the bound."""
        return len(self._entries)


failed_logins = FailedLoginTracker(
    threshold=settings.ACCOUNT_LOCK_AFTER_FAILURES,
    lock_seconds=settings.ACCOUNT_LOCK_MINUTES * 60,
)
