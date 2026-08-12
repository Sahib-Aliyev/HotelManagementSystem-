"""Password hashing and JWT creation / verification."""

import hashlib
import hmac
from datetime import timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.database import utcnow

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

#: Hash of a throwaway password, used to spend the same CPU time on a missing
#: account as on a real one. Computed once at import.
_DUMMY_HASH = pwd_context.hash("timing-equaliser-not-a-real-password")


def hash_password(plain_password: str) -> str:
    # bcrypt silently truncates past 72 bytes; reject instead of surprising the user.
    if len(plain_password.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or fewer")
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return False


def waste_password_time() -> None:
    """Run one bcrypt verification and throw the result away.

    Without this, a login for an address that does not exist returns before
    any hashing happens, so response time reveals which emails are registered
    even though both paths return the same message.
    """
    pwd_context.verify("timing-equaliser-not-a-real-password", _DUMMY_HASH)


def password_fingerprint(hashed_password: str) -> str:
    """Short, non-reversible tag identifying *which* password a token was issued for.

    Embedded in the token and re-checked on every request, so changing a
    password immediately invalidates sessions minted under the old one —
    including any an attacker still holds.
    """
    return hashlib.sha256(hashed_password.encode("utf-8")).hexdigest()[:16]


def fingerprints_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(left, right)


def create_access_token(
    subject: str | int,
    role: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expire = utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "exp": expire,
        "iat": utcnow(),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Return the token payload, or None if the token is invalid or expired."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
