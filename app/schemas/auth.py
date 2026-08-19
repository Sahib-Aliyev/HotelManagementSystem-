"""Authentication and user schemas."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.models.user import UserRole
from app.schemas.common import ORMModel

MIN_PASSWORD_LENGTH = 10


def _strong_enough(value: str) -> str:
    """Reject the passwords that make a brute-force worth attempting.

    Length alone is the strongest single factor, but staff accounts here are
    created by an admin who tends to pick something memorable, so the class
    checks stop `password11` from getting through.
    """
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must contain an upper-case letter")
    if not any(c.islower() for c in value):
        raise ValueError("Password must contain a lower-case letter")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain a digit")
    return value


#: bcrypt truncates past 72 bytes, so that is the hard ceiling everywhere.
Password = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=72),
    AfterValidator(_strong_enough),
]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: Password
    role: UserRole = UserRole.RECEPTIONIST
    phone: str | None = Field(None, max_length=30)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    email: EmailStr | None = None
    role: UserRole | None = None
    phone: str | None = Field(None, max_length=30)
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: Password


class UserRead(ORMModel):
    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    phone: str | None
    is_active: bool
