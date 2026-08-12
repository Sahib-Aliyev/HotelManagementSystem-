"""Generic async repository."""

from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)

#: Passed to `.like(..., escape=LIKE_ESCAPE)` wherever `like_pattern` is used.
LIKE_ESCAPE = "\\"


def like_pattern(term: str) -> str:
    """Build a contains-pattern with the caller's wildcards neutralised.

    `%` and `_` are wildcards in SQL LIKE, so a staff member searching for a
    literal "%" would otherwise match every row in the table.
    """
    escaped = (
        term.strip()
        .lower()
        .replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)  # first, or it double-escapes below
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, obj_id: int) -> ModelT | None:
        return await self.db.get(self.model, obj_id)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.unique().scalars())

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        return int((await self.db.execute(stmt)).scalar_one())

    async def create(self, **values: Any) -> ModelT:
        obj = self.model(**values)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: ModelT, **values: Any) -> ModelT:
        for field, value in values.items():
            if value is not None or field in getattr(obj, "_nullable_fields", ()):
                setattr(obj, field, value)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.db.delete(obj)
        await self.db.flush()
