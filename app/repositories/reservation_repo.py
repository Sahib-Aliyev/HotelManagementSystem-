"""Reservation data access."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import joinedload

from app.models.guest import Guest
from app.models.payment import Payment
from app.models.reservation import BLOCKING_STATUSES, Reservation, ReservationStatus
from app.models.room import Room
from app.repositories.base import LIKE_ESCAPE, BaseRepository, like_pattern
from app.repositories.payment_repo import is_cash_movement, signed_amount


def _with_relations(stmt: Select) -> Select:
    return stmt.options(
        joinedload(Reservation.guest),
        joinedload(Reservation.room).joinedload(Room.room_type),
    )


class ReservationRepository(BaseRepository[Reservation]):
    model = Reservation

    async def get_full(self, reservation_id: int) -> Reservation | None:
        stmt = _with_relations(select(Reservation)).where(
            Reservation.id == reservation_id
        )
        return (await self.db.execute(stmt)).unique().scalars().first()

    async def get_by_reference(self, reference: str) -> Reservation | None:
        stmt = _with_relations(select(Reservation)).where(
            Reservation.reference == reference.strip().upper()
        )
        return (await self.db.execute(stmt)).unique().scalars().first()

    async def search(
        self,
        *,
        term: str | None = None,
        status: ReservationStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        guest_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
        ascending: bool = False,
    ) -> tuple[list[Reservation], int]:
        stmt = (
            _with_relations(select(Reservation))
            .join(Guest, Reservation.guest_id == Guest.id)
            .join(Room, Reservation.room_id == Room.id)
        )
        count_stmt = (
            select(func.count())
            .select_from(Reservation)
            .join(Guest, Reservation.guest_id == Guest.id)
            .join(Room, Reservation.room_id == Room.id)
        )

        conditions = []
        if term:
            pattern = like_pattern(term)
            conditions.append(
                or_(
                    func.lower(Reservation.reference).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Guest.full_name).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Guest.phone).like(pattern, escape=LIKE_ESCAPE),
                    func.lower(Room.room_number).like(pattern, escape=LIKE_ESCAPE),
                )
            )
        if status is not None:
            conditions.append(Reservation.status == status)
        if guest_id is not None:
            conditions.append(Reservation.guest_id == guest_id)
        # Overlap semantics: any stay touching the requested window.
        if date_from is not None:
            conditions.append(Reservation.check_out_date >= date_from)
        if date_to is not None:
            conditions.append(Reservation.check_in_date <= date_to)

        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        order = (
            (Reservation.check_in_date.asc(), Reservation.id.asc())
            if ascending
            else (Reservation.check_in_date.desc(), Reservation.id.desc())
        )
        stmt = stmt.order_by(*order).limit(limit).offset(offset)
        rows = list((await self.db.execute(stmt)).unique().scalars())
        total = int((await self.db.execute(count_stmt)).scalar_one())
        return rows, total

    async def arrivals_on(self, day: date) -> list[Reservation]:
        """Everyone still expected as of `day`, earliest first.

        Deliberately `<=` and not `==`: a booking whose arrival date has passed
        without a check-in or a no-show used to match no day at all, so it
        appeared on no screen while its room stayed blocked.
        """
        stmt = (
            _with_relations(select(Reservation))
            .join(Room, Reservation.room_id == Room.id)
            .where(
                Reservation.check_in_date <= day,
                Reservation.status.in_(
                    [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]
                ),
            )
            .order_by(Reservation.check_in_date, Room.room_number)
        )
        return list((await self.db.execute(stmt)).unique().scalars())

    async def departures_on(self, day: date) -> list[Reservation]:
        """Everyone due to leave by `day`, most overdue first.

        Same reason as `arrivals_on`: with `==` an overdue guest vanished from
        the Departures column instead of being the first thing on it.
        """
        stmt = (
            _with_relations(select(Reservation))
            .where(
                Reservation.check_out_date <= day,
                Reservation.status == ReservationStatus.CHECKED_IN,
            )
            .order_by(Reservation.check_out_date, Reservation.id)
        )
        return list((await self.db.execute(stmt)).unique().scalars())

    async def in_house(self) -> list[Reservation]:
        stmt = (
            _with_relations(select(Reservation))
            .where(Reservation.status == ReservationStatus.CHECKED_IN)
            .order_by(Reservation.check_out_date)
        )
        return list((await self.db.execute(stmt)).unique().scalars())

    async def count_by_status(self, status: ReservationStatus) -> int:
        stmt = (
            select(func.count())
            .select_from(Reservation)
            .where(Reservation.status == status)
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def amount_paid(self, reservation_id: int) -> Decimal:
        """What the guest has actually paid: settled payments less refunds."""
        stmt = select(func.coalesce(func.sum(signed_amount()), 0)).where(
            Payment.reservation_id == reservation_id,
            is_cash_movement(),
        )
        return Decimal(str((await self.db.execute(stmt)).scalar_one()))

    async def next_reference_seq(self) -> int:
        """Sequence seed for human-readable booking references."""
        stmt = select(func.count()).select_from(Reservation)
        return int((await self.db.execute(stmt)).scalar_one()) + 1

    async def active_for_room(self, room_id: int) -> Reservation | None:
        """The stay currently occupying a room, if any."""
        stmt = _with_relations(select(Reservation)).where(
            Reservation.room_id == room_id,
            Reservation.status == ReservationStatus.CHECKED_IN,
        )
        return (await self.db.execute(stmt)).unique().scalars().first()

    async def upcoming_for_room(self, room_id: int) -> Reservation | None:
        """The next booking holding this room, arrival date passed or not.

        No date filter on purpose: a booking whose arrival date went by without
        a check-in still blocks the room, and filtering on `check_in_date >=
        today` left the rooms board showing "no upcoming bookings" for a room
        that could not be sold.
        """
        stmt = (
            _with_relations(select(Reservation))
            .where(
                Reservation.room_id == room_id,
                Reservation.status.in_(
                    [ReservationStatus.PENDING, ReservationStatus.CONFIRMED]
                ),
            )
            .order_by(Reservation.check_in_date)
            .limit(1)
        )
        return (await self.db.execute(stmt)).unique().scalars().first()
