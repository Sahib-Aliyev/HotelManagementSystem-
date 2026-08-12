"""Authentication and staff management endpoints."""

from fastapi import APIRouter, Request, Response, status

from app.core.config import settings
from app.core.deps import AdminUser, CurrentUser, DbSession
from app.core.ratelimit import limiter
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.schemas.common import Message
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV == "production",
        path="/",
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(
    request: Request, payload: LoginRequest, response: Response, db: DbSession
):
    """Sign in. Also sets an httpOnly cookie so the web UI works from one call.

    `request` is unused here but slowapi reads the client address off it, so
    the limiter above only works while the parameter is present.
    """
    _user, token = await AuthService(db).login(payload.email, payload.password)
    set_session_cookie(response, token.access_token)
    return token


@router.post("/logout", response_model=Message)
async def logout(response: Response):
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return Message(message="Signed out.")


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser):
    return user


@router.post("/change-password", response_model=Message)
@limiter.limit(settings.PASSWORD_CHANGE_RATE_LIMIT)
async def change_password(
    request: Request,
    payload: PasswordChange,
    response: Response,
    user: CurrentUser,
    db: DbSession,
):
    """Change the signed-in user's password and re-key this session.

    The new hash invalidates every token issued under the old password, this
    one included, so a replacement cookie is set before returning — other
    devices stay signed out, which is the point.
    """
    service = AuthService(db)
    await service.change_password(user, payload.current_password, payload.new_password)
    set_session_cookie(response, service.issue_token(user).access_token)
    return Message(message="Password updated. Other devices have been signed out.")


# ------------------------------------------------------------- staff (admin)
staff_router = APIRouter(prefix="/staff", tags=["Staff"])


@staff_router.get("", response_model=list[UserRead])
async def list_staff(db: DbSession, _admin: AdminUser):
    return await AuthService(db).list_users()


@staff_router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_staff(payload: UserCreate, db: DbSession, _admin: AdminUser):
    return await AuthService(db).create_user(payload)


@staff_router.patch("/{user_id}", response_model=UserRead)
async def update_staff(
    user_id: int, payload: UserUpdate, db: DbSession, admin: AdminUser
):
    return await AuthService(db).update_user(user_id, payload, admin)


@staff_router.delete("/{user_id}", response_model=UserRead)
async def deactivate_staff(user_id: int, db: DbSession, admin: AdminUser):
    return await AuthService(db).deactivate(user_id, admin)
