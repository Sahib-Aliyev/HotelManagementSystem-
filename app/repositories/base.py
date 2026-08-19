"""Generic async repository.

Deliberately thin. It used to carry `list()`, `count()` and an `update()` that
filtered `None` against a `_nullable_fields` attribute no model defined — a dead
branch reimplementing, badly, the rule the services do properly with their own
`NULLABLE_UPDATE_FIELDS`. Nothing called any of the three. A base class that
offers a wrong version of a rule stated correctly elsewhere is worse than one
that offers nothing.
"""

from typing import Any, Generic, TypeVar

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

    async def create(self, **values: Any) -> ModelT:
        obj = self.model(**values)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.db.delete(obj)
        await self.db.flush()
