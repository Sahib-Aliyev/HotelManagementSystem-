"""Room inventory, housekeeping status and availability search."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.room import Room, RoomStatus, RoomType
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

    async def update_type(
        self, room_type_id: int, payload: RoomTypeUpdate
    ) -> RoomType:
        room_type = await self.get_type(room_type_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"]:
            clash = await self.room_types.get_by_name(data["name"])
            if clash and clash.id != room_type_id:
                raise ConflictError("Another room type already uses that name.")
        for field, value in data.items():
            setattr(room_type, field, value)
        await self.db.commit()
        await self.db.refresh(room_type)
        return room_type

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

    async def update_room(self, room_id: int, payload: RoomUpdate) -> Room:
        room = await self.get_room(room_id)
        data = payload.model_dump(exclude_unset=True)

        if "room_number" in data and data["room_number"]:
            clash = await self.rooms.get_by_number(
                data["room_number"], exclude_id=room_id
            )
            if clash is not None:
                raise ConflictError("Another room already uses that number.")
        if "room_type_id" in data and data["room_type_id"]:
            await self.get_type(data["room_type_id"])
        if data.get("status") == RoomStatus.MAINTENANCE:
            occupant = await self.reservations.active_for_room(room_id)
            if occupant is not None:
                raise ConflictError(
                    f"Room {room.room_number} is occupied by {occupant.guest.full_name}."
                )

        for field, value in data.items():
            setattr(room, field, value)
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def set_status(self, room_id: int, status: RoomStatus) -> Room:
        return await self.update_room(room_id, RoomUpdate(status=status))

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
            item.total_price = (Decimal(room.room_type.base_price) * nights).quantize(
                Decimal("0.01")
            )
            results.append(item)
        return results

    async def status_counts(self) -> dict[RoomStatus, int]:
        return await self.rooms.status_counts()

    async def board(self) -> list[dict]:
        """Room grid for the rooms page: each room plus who is in it."""
        rooms = await self.rooms.list_all()
        board: list[dict] = []
        for room in rooms:
            occupant = await self.reservations.active_for_room(room.id)
            upcoming = (
                None
                if occupant
                else await self.reservations.upcoming_for_room(room.id)
            )
            board.append(
                {
                    "room": room,
                    "occupant": occupant,
                    "upcoming": upcoming,
                }
            )
        return board
