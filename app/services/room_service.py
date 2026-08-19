"""Room inventory, housekeeping status and availability search."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.models.room import Room, RoomStatus, RoomType
from app.models.user import User, UserRole
from app.repositories.reservation_repo import ReservationRepository
from app.repositories.room_repo import RoomRepository, RoomTypeRepository
from app.schemas.room import (
    AvailableRoom,
    RoomAvailabilityQuery,
    RoomCreate,
    RoomTypeCreate,
    RoomTypeUpdate,
    RoomUpdate,
)
from app.services.pricing import accommodation_charge


class RoomService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.rooms = RoomRepository(db)
        self.room_types = RoomTypeRepository(db)
        self.reservations = ReservationRepository(db)

    # ------------------------------------------------------------------ types
    async def list_types(self) -> list[RoomType]:
        return await self.room_types.list_all()

    async def get_type(self, room_type_id: int) -> RoomType:
        room_type = await self.room_types.get(room_type_id)
        if room_type is None:
            raise NotFoundError("Room type not found.")
        return room_type

    async def create_type(self, payload: RoomTypeCreate) -> RoomType:
        if await self.room_types.get_by_name(payload.name):
            raise ConflictError(f"A room type named '{payload.name}' already exists.")
        room_type = await self.room_types.create(
            name=payload.name.strip(),
            description=payload.description,
            base_price=payload.base_price,
            capacity=payload.capacity,
            amenities=payload.amenities,
        )
        await self.db.commit()
        return room_type

    async def update_type(self, room_type_id: int, payload: RoomTypeUpdate) -> RoomType:
        room_type = await self.get_type(room_type_id)
        data = payload.model_dump(exclude_unset=True)
        if data.get("name"):
            clash = await self.room_types.get_by_name(data["name"])
            if clash and clash.id != room_type_id:
                raise ConflictError("Another room type already uses that name.")
        if data.get("capacity") is not None:
            await self._assert_capacity_fits_bookings(room_type_id, data["capacity"])
        for field, value in data.items():
            setattr(room_type, field, value)
        await self.db.commit()
        await self.db.refresh(room_type)
        return room_type

    async def _assert_capacity_fits_bookings(
        self, room_type_id: int, new_capacity: int
    ) -> None:
        """Capacity is the ceiling every booking is validated against.

        Shrinking it under a live booking left that booking in violation of a
        rule it could no longer be edited without tripping: a Double reduced to
        capacity 1 still held a two-guest stay, and `create` and `update` would
        both refuse the same party from then on.
        """
        largest = await self.rooms.largest_party_for_type(room_type_id)
        if largest > new_capacity:
            raise ConflictError(
                f"A current or upcoming booking for this room type holds "
                f"{largest} guests, so its capacity cannot be reduced to "
                f"{new_capacity}. Move or amend that booking first.",
                details={"largest_party": largest},
            )

    # ------------------------------------------------------------------ rooms
    async def list_rooms(
        self,
        *,
        status: RoomStatus | None = None,
        room_type_id: int | None = None,
        floor: int | None = None,
    ) -> list[Room]:
        return await self.rooms.list_all(
            status=status, room_type_id=room_type_id, floor=floor
        )

    async def get_room(self, room_id: int) -> Room:
        room = await self.rooms.get(room_id)
        if room is None:
            raise NotFoundError("Room not found.")
        return room

    async def create_room(self, payload: RoomCreate) -> Room:
        await self.get_type(payload.room_type_id)
        if await self.rooms.get_by_number(payload.room_number):
            raise ConflictError(f"Room {payload.room_number} already exists.")
        room = await self.rooms.create(
            room_number=payload.room_number.strip(),
            room_type_id=payload.room_type_id,
            floor=payload.floor,
            status=payload.status,
            notes=payload.notes,
        )
        await self.db.commit()
        return await self.get_room(room.id)

    async def update_room(
        self, room_id: int, payload: RoomUpdate, *, acting_user: User | None = None
    ) -> Room:
        room = await self.get_room(room_id)
        data = payload.model_dump(exclude_unset=True)

        if data.get("room_number"):
            clash = await self.rooms.get_by_number(
                data["room_number"], exclude_id=room_id
            )
            if clash is not None:
                raise ConflictError("Another room already uses that number.")
        if data.get("room_type_id"):
            new_type = await self.get_type(data["room_type_id"])
            # Moving a room to a smaller type shrinks capacity under whatever is
            # booked in it, exactly like reducing the type's own capacity.
            largest = await self.rooms.largest_party_for_room(room_id)
            if largest > new_type.capacity:
                raise ConflictError(
                    f"A current or upcoming booking in room {room.room_number} "
                    f"holds {largest} guests, which does not fit "
                    f"{new_type.name} (sleeps up to {new_type.capacity}).",
                    details={"largest_party": largest},
                )
        if data.get("status") == RoomStatus.MAINTENANCE:
            await self._assert_may_take_out_of_service(room, acting_user)

        # A room with a guest checked into it is never "available". Housekeeping
        # cleans occupied rooms every day, and marking one clean used to put it
        # back on the sale floor while the guest was still in it: the card read
        # AVAILABLE, the guest was listed on it, and booking failed with a
        # conflict nobody could explain. Cleaning an occupied room returns it to
        # OCCUPIED instead.
        if data.get("status") == RoomStatus.AVAILABLE and (
            await self.reservations.active_for_room(room_id)
        ):
            data["status"] = RoomStatus.OCCUPIED

        for field, value in data.items():
            setattr(room, field, value)
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def _assert_may_take_out_of_service(
        self, room: Room, acting_user: User | None
    ) -> None:
        """Removing a room from sale is a commercial decision, not housekeeping.

        Two doors used to reach this state with different locks:
        `PATCH /rooms/{id}` was manager-only while `POST /rooms/{id}/status` was
        open to any staff member, so a receptionist refused by one was admitted
        by the other. The role belongs to the change, not to the route, so the
        check lives here — the same reasoning as
        `ReservationService._assert_may_set_rate`.
        """
        if acting_user is not None and acting_user.role not in (
            UserRole.ADMIN,
            UserRole.MANAGER,
        ):
            raise PermissionDeniedError(
                "Only a manager or administrator can take a room out of service. "
                "Flag it for cleaning instead, or ask a manager."
            )

        occupants = await self.reservations.active_for_room(room.id)
        if occupants:
            names = ", ".join(r.guest.full_name for r in occupants)
            raise ConflictError(f"Room {room.room_number} is occupied by {names}.")

        # A future booking does not stop the room going out of service silently,
        # which left the booking alive and unfulfillable: nothing said so until
        # the guest arrived and check-in refused, because the room was no longer
        # bookable. Name the stays so someone rehouses them now.
        blocked = await self.reservations.blocking_for_room(room.id)
        if blocked:
            listed = ", ".join(
                f"{r.reference} ({r.check_in_date.isoformat()})" for r in blocked[:3]
            )
            more = f" and {len(blocked) - 3} more" if len(blocked) > 3 else ""
            raise ConflictError(
                f"Room {room.room_number} has {len(blocked)} booking(s) that "
                f"would become unfulfillable: {listed}{more}. Move or cancel "
                "them before taking the room out of service.",
                details={"blocked_reservations": [r.reference for r in blocked]},
            )

    async def set_status(
        self, room_id: int, status: RoomStatus, *, acting_user: User | None = None
    ) -> Room:
        """Housekeeping status. Returns the room, whose status may differ from
        the one asked for — see the occupancy rule in `update_room`."""
        return await self.update_room(
            room_id, RoomUpdate(status=status), acting_user=acting_user
        )

    async def delete_room(self, room_id: int) -> None:
        room = await self.get_room(room_id)
        future = await self.reservations.upcoming_for_room(room_id)
        if future is not None or await self.reservations.active_for_room(room_id):
            raise ConflictError(
                "This room has current or upcoming reservations and cannot be deleted."
            )
        await self.rooms.delete(room)
        await self.db.commit()

    # ----------------------------------------------------------- availability
    async def find_available(
        self, query: RoomAvailabilityQuery, *, exclude_reservation_id: int | None = None
    ) -> list[AvailableRoom]:
        if query.check_in_date < date.today():
            raise ValidationError("Check-in date cannot be in the past.")

        rooms = await self.rooms.find_available(
            query.check_in_date,
            query.check_out_date,
            room_type_id=query.room_type_id,
            capacity=query.capacity,
            exclude_reservation_id=exclude_reservation_id,
        )
        nights = query.nights
        results: list[AvailableRoom] = []
        for room in rooms:
            item = AvailableRoom.model_validate(room)
            item.nights = nights
            item.total_price = accommodation_charge(room.room_type.base_price, nights)
            results.append(item)
        return results

    async def status_counts(self) -> dict[RoomStatus, int]:
        return await self.rooms.status_counts()
