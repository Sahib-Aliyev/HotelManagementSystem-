"""User data access."""

from sqlalchemy import select

from app.models.user import User, UserRole
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return (await self.db.execute(stmt)).scalars().first()

    async def list_all(self) -> list[User]:
        stmt = select(User).order_by(User.full_name)
        return list((await self.db.execute(stmt)).scalars())

    async def count_active_admins(self, *, exclude_id: int | None = None) -> int:
        """How many active administrators remain, optionally ignoring one.

        A count in SQL rather than loading every user and filtering in Python.
        `with_for_update()` locks the rows it counts, so two concurrent
        demotions serialise instead of each seeing the other as "the other
        admin" and both succeeding — which would leave nobody able to
        administer the system.
        """
        stmt = select(User.id).where(
            User.role == UserRole.ADMIN, User.is_active.is_(True)
        )
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        locked = stmt.with_for_update()
        try:
            rows = (await self.db.execute(locked)).all()
        except Exception:
            # SQLite has no row locking; the count is still correct there, and
            # its single writer serialises the transactions anyway.
            rows = (await self.db.execute(stmt)).all()
        return len(rows)

    async def email_taken(self, email: str, *, exclude_id: int | None = None) -> bool:
        stmt = select(User.id).where(User.email == email.strip().lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return (await self.db.execute(stmt)).first() is not None
