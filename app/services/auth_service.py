"""Authentication and staff-account management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.security import (
    create_access_token,
    hash_password,
    password_fingerprint,
    verify_password,
    waste_password_time,
)
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenResponse, UserCreate, UserUpdate


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        # Same message either way so the response cannot be used to probe
        # which email addresses exist. The unknown-account branch still pays
        # for one bcrypt round, otherwise its faster reply leaks the same fact
        # the shared message is hiding.
        if user is None:
            waste_password_time()
            raise AuthenticationError("Incorrect email or password.")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Incorrect email or password.")
        if not user.is_active:
            raise PermissionDeniedError("This account has been deactivated.")
        return user

    def issue_token(self, user: User) -> TokenResponse:
        token = create_access_token(
            subject=user.id,
            role=user.role.value,
            extra_claims={"pwf": password_fingerprint(user.hashed_password)},
        )
        return TokenResponse(
            access_token=token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def login(self, email: str, password: str) -> tuple[User, TokenResponse]:
        user = await self.authenticate(email, password)
        return user, self.issue_token(user)

    async def create_user(self, payload: UserCreate) -> User:
        email = payload.email.strip().lower()
        if await self.users.email_taken(email):
            raise ConflictError(f"An account with {email} already exists.")
        user = await self.users.create(
            full_name=payload.full_name.strip(),
            email=email,
            hashed_password=hash_password(payload.password),
            role=payload.role,
            phone=payload.phone,
        )
        await self.db.commit()
        return user

    async def _assert_not_last_admin(self, user: User, action: str) -> None:
        """Block changes that would leave the system with no way to administer it."""
        if user.role != UserRole.ADMIN or not user.is_active:
            return
        other_admins = [
            u
            for u in await self.users.list_all()
            if u.role == UserRole.ADMIN and u.is_active and u.id != user.id
        ]
        if not other_admins:
            raise ConflictError(f"The last active administrator cannot be {action}.")

    async def update_user(
        self, user_id: int, payload: UserUpdate, acting_user: User
    ) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("Staff member not found.")

        # These two guards also live in deactivate(); PATCH reaches the same
        # state through `role` and `is_active`, so it needs them as well.
        if payload.is_active is False and user.is_active:
            if user.id == acting_user.id:
                raise ConflictError("You cannot deactivate your own account.")
            await self._assert_not_last_admin(user, "deactivated")

        if payload.role is not None and payload.role != user.role:
            if user.id == acting_user.id:
                raise ConflictError("You cannot change your own role.")
            await self._assert_not_last_admin(user, "demoted")

        if payload.email and payload.email.strip().lower() != user.email:
            if await self.users.email_taken(payload.email, exclude_id=user_id):
                raise ConflictError("That email is already in use.")
            user.email = payload.email.strip().lower()

        if payload.full_name is not None:
            user.full_name = payload.full_name.strip()
        if payload.role is not None:
            user.role = payload.role
        if payload.phone is not None:
            user.phone = payload.phone
        if payload.is_active is not None:
            user.is_active = payload.is_active

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect.")
        if verify_password(new_password, user.hashed_password):
            raise ValidationError("The new password must differ from the current one.")
        # Changing the hash changes the token fingerprint, so every session
        # issued under the old password stops working on its next request.
        user.hashed_password = hash_password(new_password)
        await self.db.commit()

    async def deactivate(self, user_id: int, acting_user: User) -> User:
        if user_id == acting_user.id:
            raise ConflictError("You cannot deactivate your own account.")
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("Staff member not found.")
        if user.role == UserRole.ADMIN:
            admins = [
                u
                for u in await self.users.list_all()
                if u.role == UserRole.ADMIN and u.is_active
            ]
            if len(admins) <= 1:
                raise ConflictError("The last active administrator cannot be removed.")
        user.is_active = False
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def list_users(self) -> list[User]:
        return await self.users.list_all()
