"""Raw SQL in a migration must agree with what the ORM actually stores.

This file exists because of a bug that shipped and was caught afterwards. The
`no_double_booking` exclusion constraint added on 2026-08-19 was written with

    WHERE (status IN ('pending','confirmed','checked_in'))

taking the strings from `ReservationStatus.*.value`. But SQLAlchemy's `Enum`
persists a Python enum by its **name**, so the column actually holds
`'CONFIRMED'`, not `'confirmed'`. The predicate therefore matched no row ever:
the constraint was created, appeared in the table definition, and guarded
nothing. `CREATE` succeeded, `alembic check` was clean, every test passed, and
the race the constraint existed to close was still wide open.

Nothing in the suite could see it. The constraint is PostgreSQL-only, so SQLite
skips that branch entirely, and the PostgreSQL test would only have failed on a
machine with PostgreSQL. What is checked here instead is the *literal itself*,
against what the ORM emits — which needs no database at all and so runs
everywhere.

The general rule: hand-written SQL that names an enum value is a second source
of truth for something the ORM already decides. Either avoid it, or pin it here.
"""

import importlib.util
import pathlib
import re

import pytest
from sqlalchemy.dialects import postgresql

from app.models.reservation import BLOCKING_STATUSES, Reservation

MIGRATION = (
    pathlib.Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "c58d31ea7f04_audit_of_2026_08_19_integrity_and_indexes.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_audit_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stored_blocking_values() -> set[str]:
    """The strings SQLAlchemy really puts in the column for BLOCKING_STATUSES."""
    compiled = (
        Reservation.__table__.select()
        .where(Reservation.status.in_(BLOCKING_STATUSES))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    where = str(compiled).split("WHERE", 1)[1]
    return set(re.findall(r"'([^']+)'", where))


def test_the_migration_matches_what_the_orm_stores():
    module = _load_migration()
    in_migration = set(re.findall(r"'([^']+)'", module.BLOCKING))
    assert in_migration == _stored_blocking_values(), (
        "the exclusion constraint's status literals do not match the values "
        "SQLAlchemy writes, so the constraint would guard nothing"
    )


def test_the_migration_covers_every_blocking_status():
    """A status missing from the predicate is a room that can be sold twice."""
    module = _load_migration()
    in_migration = set(re.findall(r"'([^']+)'", module.BLOCKING))
    assert in_migration == {
        s.name for s in BLOCKING_STATUSES
    }, "BLOCKING_STATUSES and the constraint's WHERE clause have diverged"


def test_enum_columns_store_names_not_values():
    """The fact the bug turned on, pinned so it cannot quietly change.

    If a future SQLAlchemy release or a `values_callable` argument switched this
    to storing values, every hand-written literal in a migration would flip
    meaning at once — including the one above.
    """
    from app.models.reservation import ReservationStatus

    assert ReservationStatus.CONFIRMED.value == "confirmed"
    assert "CONFIRMED" in _stored_blocking_values()
    assert "confirmed" not in _stored_blocking_values()


@pytest.mark.parametrize(
    "literal",
    ["'pending'", "'confirmed'", "'checked_in'", "'paid'", "'cancelled'"],
)
def test_no_lower_case_status_literal_survives_in_the_migration(literal):
    """Catches the original mistake by shape, not only by comparison."""
    source = MIGRATION.read_text(encoding="utf-8")
    # Comments explain the bug and quote the wrong form on purpose.
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert (
        literal not in code
    ), f"{literal} is a lower-case enum value; the column stores the name"
