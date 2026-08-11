"""Room and room-type endpoints."""

from datetime import date

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, ManagerUser, StaffUser
from app.models.room import RoomStatus
from app.schemas.common import Message
from app.schemas.room import (
    AvailableRoom,
    RoomAvailabilityQuery,
    RoomCreate,
    RoomRead,
    RoomTypeCreate,
    RoomTypeRead,
    RoomTypeUpdate,
    RoomUpdate,
)
from app.services.room_service import RoomService

router = APIRouter(prefix="/rooms", tags=["Rooms"])
types_router = APIRouter(prefix="/room-types", tags=["Room types"])


@router.get("", response_model=list[RoomRead])
async def list_rooms(
    db: DbSession,
    _user: StaffUser,
    room_status: RoomStatus | None = Query(None, alias="status"),
    room_type_id: int | None = None,
    floor: int | None = None,
):
    return await RoomService(db).list_rooms(
        status=room_status, room_type_id=room_type_id, floor=floor
    )


@router.get("/availability", response_model=list[AvailableRoom])
async def check_availability(
    db: DbSession,
    _user: StaffUser,
    check_in_date: date,
    check_out_date: date,
    room_type_id: int | None = None,
    capacity: int | None = Query(None, ge=1),
    exclude_reservation_id: int | None = None,
):
    """Rooms that can be sold for the whole range, with the price for the stay."""
    query = RoomAvailabilityQuery(
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        room_type_id=room_type_id,
        capacity=capacity,
    )
    return await RoomService(db).find_available(
        query, exclude_reservation_id=exclude_reservation_id
    )


@router.get("/status-summary", response_model=dict[str, int])
async def status_summary(db: DbSession, _user: StaffUser):
    counts = await RoomService(db).status_counts()
    return {status.value: count for status, count in counts.items()}


@router.post("", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
async def create_room(payload: RoomCreate, db: DbSession, _manager: ManagerUser):
    return await RoomService(db).create_room(payload)


@router.get("/{room_id}", response_model=RoomRead)
async def get_room(room_id: int, db: DbSession, _user: StaffUser):
    return await RoomService(db).get_room(room_id)


@router.patch("/{room_id}", response_model=RoomRead)
async def update_room(
    room_id: int, payload: RoomUpdate, db: DbSession, _manager: ManagerUser
):
    return await RoomService(db).update_room(room_id, payload)


@router.post("/{room_id}/status", response_model=RoomRead)
async def set_room_status(
    room_id: int, new_status: RoomStatus, db: DbSession, _user: StaffUser
):
    """Housekeeping can flip a room between available / cleaning / maintenance."""
    return await RoomService(db).set_status(room_id, new_status)


@router.delete("/{room_id}", response_model=Message)
async def delete_room(room_id: int, db: DbSession, _manager: ManagerUser):
    await RoomService(db).delete_room(room_id)
    return Message(message="Room deleted.")


# ---------------------------------------------------------------- room types
@types_router.get("", response_model=list[RoomTypeRead])
async def list_room_types(db: DbSession, _user: StaffUser):
    return await RoomService(db).list_types()


@types_router.post("", response_model=RoomTypeRead, status_code=status.HTTP_201_CREATED)
async def create_room_type(
    payload: RoomTypeCreate, db: DbSession, _manager: ManagerUser
):
    return await RoomService(db).create_type(payload)


@types_router.patch("/{room_type_id}", response_model=RoomTypeRead)
async def update_room_type(
    room_type_id: int, payload: RoomTypeUpdate, db: DbSession, _manager: ManagerUser
):
    return await RoomService(db).update_type(room_type_id, payload)
