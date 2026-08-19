"""Reservation endpoints, including the check-in / check-out workflow."""

from datetime import date

from fastapi import APIRouter, Query, status

from app.core.deps import DbSession, ManagerUser, StaffUser
from app.models.reservation import ReservationStatus
from app.schemas.common import Page
from app.schemas.reservation import (
    QuickBookingCreate,
    ReservationCancel,
    ReservationCheckOut,
    ReservationCreate,
    ReservationRead,
    ReservationUpdate,
    ReservationWithBalance,
)
from app.services.guest_service import GuestService
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/reservations", tags=["Reservations"])


async def _with_balance(
    service: ReservationService, reservation
) -> ReservationWithBalance:
    paid, due = await service.balance(reservation)
    data = ReservationRead.model_validate(reservation).model_dump()
    return ReservationWithBalance(**data, amount_paid=paid, balance_due=due)


@router.get("", response_model=Page[ReservationRead])
async def search_reservations(
    db: DbSession,
    _user: StaffUser,
    q: str | None = Query(None, description="Reference, guest name, phone or room"),
    reservation_status: ReservationStatus | None = Query(None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    guest_id: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    order: str = Query("desc", pattern="^(asc|desc)$", description="Sort by check-in date"),
):
    rows, total = await ReservationService(db).search(
        term=q,
        status=reservation_status,
        date_from=date_from,
        date_to=date_to,
        guest_id=guest_id,
        limit=size,
        offset=(page - 1) * size,
        ascending=order == "asc",
    )
    return Page[ReservationRead](
        items=[ReservationRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
    )


@router.post("", response_model=ReservationRead, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: ReservationCreate, db: DbSession, user: StaffUser
):
    return await ReservationService(db).create(payload, created_by=user)


@router.post(
    "/walk-in", response_model=ReservationRead, status_code=status.HTTP_201_CREATED
)
async def create_walk_in(
    payload: QuickBookingCreate, db: DbSession, user: StaffUser
):
    """Register a new guest and book them in a single request."""
    guest = await GuestService(db).get_or_create(payload.guest)
    return await ReservationService(db).create(
        ReservationCreate(
            guest_id=guest.id,
            room_id=payload.room_id,
            check_in_date=payload.check_in_date,
            check_out_date=payload.check_out_date,
            adults=payload.adults,
            children=payload.children,
            special_requests=payload.special_requests,
            nightly_rate=payload.nightly_rate,
        ),
        created_by=user,
    )


@router.get("/front-desk")
async def front_desk(db: DbSession, _user: StaffUser):
    """Today's arrivals, departures and in-house list."""
    board = await ReservationService(db).front_desk()
    return {
        "date": board["date"],
        "arrivals": [ReservationRead.model_validate(r) for r in board["arrivals"]],
        "departures": [ReservationRead.model_validate(r) for r in board["departures"]],
        "in_house": [ReservationRead.model_validate(r) for r in board["in_house"]],
    }


@router.get("/by-reference/{reference}", response_model=ReservationWithBalance)
async def get_by_reference(reference: str, db: DbSession, _user: StaffUser):
    service = ReservationService(db)
    return await _with_balance(service, await service.get_by_reference(reference))


@router.get("/{reservation_id}", response_model=ReservationWithBalance)
async def get_reservation(reservation_id: int, db: DbSession, _user: StaffUser):
    service = ReservationService(db)
    return await _with_balance(service, await service.get(reservation_id))


@router.patch("/{reservation_id}", response_model=ReservationRead)
async def update_reservation(
    reservation_id: int, payload: ReservationUpdate, db: DbSession, user: StaffUser
):
    return await ReservationService(db).update(
        reservation_id, payload, acting_user=user
    )


@router.post("/{reservation_id}/check-in", response_model=ReservationRead)
async def check_in(reservation_id: int, db: DbSession, _user: StaffUser):
    return await ReservationService(db).check_in(reservation_id)


@router.post("/{reservation_id}/check-out", response_model=ReservationRead)
async def check_out(
    reservation_id: int,
    db: DbSession,
    user: StaffUser,
    payload: ReservationCheckOut | None = None,
):
    """Check a guest out. Writing off an outstanding balance is manager-only and
    is recorded — the role check lives in the service, which knows the balance."""
    return await ReservationService(db).check_out(
        reservation_id,
        allow_outstanding_balance=bool(payload and payload.allow_outstanding_balance),
        acting_user=user,
    )


@router.post("/{reservation_id}/cancel", response_model=ReservationRead)
async def cancel(
    reservation_id: int,
    payload: ReservationCancel,
    db: DbSession,
    user: StaffUser,
):
    """Cancelling a stay that is already checked in is a manager action —
    the role check lives in the service, which knows the status."""
    return await ReservationService(db).cancel(
        reservation_id,
        payload.reason,
        waive_balance=payload.waive_balance,
        acting_user=user,
    )


@router.post("/{reservation_id}/no-show", response_model=ReservationRead)
async def mark_no_show(reservation_id: int, db: DbSession, _manager: ManagerUser):
    return await ReservationService(db).mark_no_show(reservation_id)
