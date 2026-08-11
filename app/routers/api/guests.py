"""Guest endpoints."""

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, ManagerUser, StaffUser
from app.schemas.common import Message, Page
from app.schemas.guest import GuestCreate, GuestRead, GuestUpdate
from app.schemas.reservation import ReservationRead
from app.services.guest_service import GuestService

router = APIRouter(prefix="/guests", tags=["Guests"])


@router.get("", response_model=Page[GuestRead])
async def search_guests(
    db: DbSession,
    _user: StaffUser,
    q: str | None = Query(None, description="Name, phone, email or document number"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    rows, total = await GuestService(db).search(q, limit=size, offset=(page - 1) * size)
    return Page[GuestRead](
        items=[GuestRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
    )


@router.post("", response_model=GuestRead, status_code=status.HTTP_201_CREATED)
async def create_guest(payload: GuestCreate, db: DbSession, _user: StaffUser):
    return await GuestService(db).create(payload)


@router.get("/{guest_id}", response_model=GuestRead)
async def get_guest(guest_id: int, db: DbSession, _user: StaffUser):
    return await GuestService(db).get(guest_id)


@router.patch("/{guest_id}", response_model=GuestRead)
async def update_guest(
    guest_id: int, payload: GuestUpdate, db: DbSession, _user: StaffUser
):
    return await GuestService(db).update(guest_id, payload)


@router.get("/{guest_id}/reservations", response_model=list[ReservationRead])
async def guest_history(guest_id: int, db: DbSession, _user: StaffUser):
    return await GuestService(db).history(guest_id)


@router.delete("/{guest_id}", response_model=Message)
async def delete_guest(guest_id: int, db: DbSession, _manager: ManagerUser):
    await GuestService(db).delete(guest_id)
    return Message(message="Guest deleted.")
