"""User data access."""

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return (await self.db.execute(stmt)).scalars().first()

    async def list_all(self) -> list[User]:
        stmt = select(User).order_by(User.full_name)
        return list((await self.db.execute(stmt)).scalars())

    async def email_taken(self, email: str, *, exclude_id: int | None = None) -> bool:
        stmt = select(User.id).where(User.email == email.strip().lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return (await self.db.execute(stmt)).first() is not None
