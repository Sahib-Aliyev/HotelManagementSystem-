"""Room and room-type data access, including the availability query."""

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import joinedload

from app.models.reservation import BLOCKING_STATUSES, Reservation
from app.models.room import Room, RoomStatus, RoomType
from app.repositories.base import BaseRepository


def overlapping_reservations(
    check_in: date, check_out: date, *, exclude_reservation_id: int | None = None
):
    """A SELECT of reservation ids that collide with the given date range.

    Two stays overlap when each starts before the other ends. Same-day
    turnover (one guest leaves the morning another arrives) is *not* an
    overlap, which is why the comparisons are strict.
    """
    stmt = select(Reservation.id).where(
        Reservation.status.in_(BLOCKING_STATUSES),
        Reservation.check_in_date < check_out,
        Reservation.check_out_date > check_in,
    )
    if exclude_reservation_id is not None:
        stmt = stmt.where(Reservation.id != exclude_reservation_id)
    return stmt


class RoomTypeRepository(BaseRepository[RoomType]):
    model = RoomType

    async def list_all(self) -> list[RoomType]:
        stmt = select(RoomType).order_by(RoomType.base_price)
        return list((await self.db.execute(stmt)).scalars())

    async def get_by_name(self, name: str) -> RoomType | None:
        stmt = select(RoomType).where(func.lower(RoomType.name) == name.strip().lower())
        return (await self.db.execute(stmt)).scalars().first()


class RoomRepository(BaseRepository[Room]):
    model = Room

    async def list_all(
        self,
        *,
        status: RoomStatus | None = None,
        room_type_id: int | None = None,
        floor: int | None = None,
    ) -> list[Room]:
        stmt = select(Room).options(joinedload(Room.room_type))
        if status is not None:
            stmt = stmt.where(Room.status == status)
        if room_type_id is not None:
            stmt = stmt.where(Room.room_type_id == room_type_id)
        if floor is not None:
            stmt = stmt.where(Room.floor == floor)
        stmt = stmt.order_by(Room.floor, Room.room_number)
        return list((await self.db.execute(stmt)).unique().scalars())

    async def get_by_number(
        self, room_number: str, *, exclude_id: int | None = None
    ) -> Room | None:
        stmt = select(Room).where(Room.room_number == room_number.strip())
        if exclude_id is not None:
            stmt = stmt.where(Room.id != exclude_id)
        return (await self.db.execute(stmt)).unique().scalars().first()

    async def find_available(
        self,
        check_in: date,
        check_out: date,
        *,
        room_type_id: int | None = None,
        capacity: int | None = None,
        exclude_reservation_id: int | None = None,
    ) -> list[Room]:
        """Rooms that are sellable for the whole range."""
        busy_room_ids = select(Reservation.room_id).where(
            Reservation.id.in_(
                overlapping_reservations(
                    check_in, check_out, exclude_reservation_id=exclude_reservation_id
                )
            )
        )

        stmt = (
            select(Room)
            .join(RoomType)
            .options(joinedload(Room.room_type))
            .where(
                Room.status != RoomStatus.MAINTENANCE,
                Room.id.notin_(busy_room_ids),
            )
        )
        if room_type_id is not None:
            stmt = stmt.where(Room.room_type_id == room_type_id)
        if capacity is not None:
            stmt = stmt.where(RoomType.capacity >= capacity)

        stmt = stmt.order_by(RoomType.base_price, Room.room_number)
        return list((await self.db.execute(stmt)).unique().scalars())

    async def is_available(
        self,
        room_id: int,
        check_in: date,
        check_out: date,
        *,
        exclude_reservation_id: int | None = None,
    ) -> bool:
        stmt = select(Reservation.id).where(
            Reservation.room_id == room_id,
            Reservation.id.in_(
                overlapping_reservations(
                    check_in, check_out, exclude_reservation_id=exclude_reservation_id
                )
            ),
        )
        clash = (await self.db.execute(stmt)).first()
        return clash is None

    async def status_counts(self) -> dict[RoomStatus, int]:
        stmt = select(Room.status, func.count(Room.id)).group_by(Room.status)
        rows = (await self.db.execute(stmt)).all()
        counts = {status: 0 for status in RoomStatus}
        for status, count in rows:
            counts[status] = int(count)
        return counts

    async def occupied_on(self, day: date) -> int:
        """How many rooms are sold for the night beginning on `day`."""
        stmt = (
            select(func.count(func.distinct(Reservation.room_id)))
            .where(
                Reservation.status.in_(BLOCKING_STATUSES),
                and_(
                    Reservation.check_in_date <= day,
                    Reservation.check_out_date > day,
                ),
            )
        )
        return int((await self.db.execute(stmt)).scalar_one())
