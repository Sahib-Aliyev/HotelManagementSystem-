"""The double-booking race, proved closed — PostgreSQL only.

The invariant the reservation module names as its purpose is that a room is never
sold twice for the same night, and until the 2026-08-19 audit it lived only in
Python: `_assert_room_free` reads, then the insert writes, and two requests
arriving together both read "free". SQLite serialises writers so the interleaving
cannot even be staged there, and it cannot express an exclusion constraint, so
this file is skipped unless `DATABASE_URL` points at PostgreSQL.

`tests/test_reservations.py` covers the application-level check and the
`IntegrityError → 409` translation on either engine. What is only testable here
is the part that actually closes the race: the database refusing the second row.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Reservation, ReservationStatus

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        settings.is_sqlite,
        reason="the exclusion constraint is PostgreSQL-only; run with DATABASE_URL "
        "pointed at PostgreSQL",
    ),
]

TOMORROW = date.today() + timedelta(days=1)


def _stay(reference: str, room_id: int, guest_id: int) -> Reservation:
    return Reservation(
        reference=reference,
        guest_id=guest_id,
        room_id=room_id,
        check_in_date=TOMORROW,
        check_out_date=TOMORROW + timedelta(days=3),
        adults=1,
        status=ReservationStatus.CONFIRMED,
        nightly_rate=Decimal("150.00"),
        total_price=Decimal("450.00"),
    )


@pytest.fixture
async def pg_sessions():
    """Two independent sessions, so their transactions are genuinely concurrent."""
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def fixtures(pg_sessions):
    """A guest and a room to fight over, cleaned up afterwards."""
    from app.models import Guest, Room, RoomType

    async with pg_sessions() as db:
        room_type = RoomType(
            name=f"PGTest-{TOMORROW.isoformat()}",
            base_price=Decimal("150.00"),
            capacity=2,
            amenities=[],
        )
        db.add(room_type)
        await db.flush()
        room = Room(room_number="PG-1", room_type_id=room_type.id, floor=9)
        guest_a = Guest(
            full_name="Race A", phone="+994500000101", document_number="PGRACEA"
        )
        guest_b = Guest(
            full_name="Race B", phone="+994500000102", document_number="PGRACEB"
        )
        db.add_all([room, guest_a, guest_b])
        await db.commit()
        ids = (room.id, guest_a.id, guest_b.id, room_type.id)

    yield ids

    async with pg_sessions() as db:
        await db.execute(
            Reservation.__table__.delete().where(Reservation.room_id == ids[0])
        )
        await db.execute(Room.__table__.delete().where(Room.id == ids[0]))
        await db.execute(RoomType.__table__.delete().where(RoomType.id == ids[3]))
        await db.execute(Guest.__table__.delete().where(Guest.id.in_(ids[1:3])))
        await db.commit()


async def test_the_database_refuses_the_second_of_two_racing_bookings(
    pg_sessions, fixtures
):
    room_id, guest_a, guest_b, _ = fixtures

    async def insert(reference: str, guest_id: int, ready: asyncio.Event):
        async with pg_sessions() as db:
            db.add(_stay(reference, room_id, guest_id))
            await db.flush()
            # Both rows now exist uncommitted in their own transactions, which is
            # exactly the window the application-level check cannot see.
            ready.set()
            await asyncio.sleep(0.05)
            await db.commit()

    ready_a, ready_b = asyncio.Event(), asyncio.Event()
    results = await asyncio.gather(
        insert("PGRACE-A", guest_a, ready_a),
        insert("PGRACE-B", guest_b, ready_b),
        return_exceptions=True,
    )

    failures = [r for r in results if isinstance(r, IntegrityError)]
    assert len(failures) == 1, (
        "exactly one of the two concurrent bookings must be refused; " f"got {results}"
    )
    assert "no_double_booking" in str(failures[0].orig)

    async with pg_sessions() as db:
        rows = (
            await db.execute(
                Reservation.__table__.select().where(
                    Reservation.room_id == room_id,
                    Reservation.status == ReservationStatus.CONFIRMED,
                )
            )
        ).all()
    assert len(rows) == 1, "one room-night, one booking"


async def test_same_day_turnover_is_still_legal(pg_sessions, fixtures):
    """The constraint uses `'[)'`, so a stay ending the day another begins is
    not an overlap — the same semantics the application's strict comparisons
    already had. A constraint that broke turnover would be worse than none."""
    room_id, guest_a, guest_b, _ = fixtures

    async with pg_sessions() as db:
        first = _stay("PGTURN-A", room_id, guest_a)
        db.add(first)
        await db.commit()

    async with pg_sessions() as db:
        second = _stay("PGTURN-B", room_id, guest_b)
        second.check_in_date = first.check_out_date
        second.check_out_date = first.check_out_date + timedelta(days=2)
        db.add(second)
        await db.commit()  # must not raise

    async with pg_sessions() as db:
        rows = (
            await db.execute(
                Reservation.__table__.select().where(Reservation.room_id == room_id)
            )
        ).all()
    assert len(rows) == 2


async def test_a_cancelled_stay_releases_its_nights(pg_sessions, fixtures):
    """The constraint is partial — `WHERE status IN (…)` — so cancelling frees
    the room rather than blocking it for ever."""
    room_id, guest_a, guest_b, _ = fixtures

    async with pg_sessions() as db:
        first = _stay("PGCANCEL-A", room_id, guest_a)
        db.add(first)
        await db.commit()
        first.status = ReservationStatus.CANCELLED
        await db.commit()

    async with pg_sessions() as db:
        db.add(_stay("PGCANCEL-B", room_id, guest_b))
        await db.commit()  # the same nights, and must not raise
