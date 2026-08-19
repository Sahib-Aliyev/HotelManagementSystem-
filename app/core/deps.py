"""Shared FastAPI dependencies: current user, role guards."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import (
    decode_access_token,
    fingerprints_match,
    password_fingerprint,
)
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _extract_token(request: Request) -> str | None:
    """Accept either an `Authorization: Bearer` header (API) or the session cookie (web)."""
    header = request.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(settings.SESSION_COOKIE_NAME)


async def get_current_user(request: Request, db: DbSession) -> User:
    token = _extract_token(request)
    if not token:
        raise AuthenticationError("Not authenticated.")

    payload = decode_access_token(token)
    if not payload or payload.get("type") != "access":
        raise AuthenticationError("Invalid or expired session.")

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise AuthenticationError("Malformed token.") from None

    user = await UserRepository(db).get(user_id)
    if user is None:
        raise AuthenticationError("Account no longer exists.")
    if not user.is_active:
        raise PermissionDeniedError("This account has been deactivated.")
    if not fingerprints_match(payload.get("pwf"), password_fingerprint(user.hashed_password)):
        raise AuthenticationError("Your password changed. Please sign in again.")
    # Bumped on sign-out, which is what makes logout actually revoke the token.
    if int(payload.get("tv", 0)) != int(user.token_version or 0):
        raise AuthenticationError("This session was signed out. Please sign in again.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(request: Request, db: DbSession) -> User | None:
    """Like get_current_user but returns None instead of raising — for public pages."""
    try:
        return await get_current_user(request, db)
    except (AuthenticationError, PermissionDeniedError):
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_roles(*allowed: UserRole):
    """Dependency factory guarding an endpoint behind one or more roles."""

    async def _guard(user: CurrentUser) -> User:
        if user.role not in allowed:
            allowed_names = ", ".join(r.value for r in allowed)
            raise PermissionDeniedError(
                f"This action requires one of these roles: {allowed_names}."
            )
        return user

    return _guard


# Convenience aliases used across routers. Annotate a parameter with one of
# these and the role check runs before the handler body.
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
ManagerUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
StaffUser = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.RECEPTIONIST)),
]
