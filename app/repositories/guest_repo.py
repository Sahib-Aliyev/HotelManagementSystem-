"""Guest data access."""

from sqlalchemy import func, or_, select

from app.models.guest import DocumentType, Guest
from app.repositories.base import LIKE_ESCAPE, BaseRepository, like_pattern


class GuestRepository(BaseRepository[Guest]):
    model = Guest

    async def search(
        self, term: str | None = None, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[Guest], int]:
        """Match name, phone, email or document number; returns (rows, total)."""
        stmt = select(Guest)
        count_stmt = select(func.count()).select_from(Guest)

        if term:
            pattern = like_pattern(term)
            condition = or_(
                func.lower(Guest.full_name).like(pattern, escape=LIKE_ESCAPE),
                func.lower(Guest.phone).like(pattern, escape=LIKE_ESCAPE),
                func.lower(Guest.email).like(pattern, escape=LIKE_ESCAPE),
                func.lower(Guest.document_number).like(pattern, escape=LIKE_ESCAPE),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(Guest.full_name).limit(limit).offset(offset)
        rows = list((await self.db.execute(stmt)).scalars())
        total = int((await self.db.execute(count_stmt)).scalar_one())
        return rows, total

    async def get_by_document(
        self,
        document_type: DocumentType,
        document_number: str,
        *,
        exclude_id: int | None = None,
    ) -> Guest | None:
        stmt = select(Guest).where(
            Guest.document_type == document_type,
            Guest.document_number == document_number.replace(" ", "").upper(),
        )
        if exclude_id is not None:
            stmt = stmt.where(Guest.id != exclude_id)
        return (await self.db.execute(stmt)).scalars().first()
