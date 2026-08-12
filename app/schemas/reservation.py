"""Reservation schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.reservation import ReservationStatus
from app.schemas.common import ORMModel
from app.schemas.guest import GuestCreate, GuestSummary
from app.schemas.room import RoomRead


class ReservationCreate(BaseModel):
    guest_id: int
    room_id: int
    check_in_date: date
    check_out_date: date
    adults: int = Field(1, ge=1, le=10)
    children: int = Field(0, ge=0, le=10)
    special_requests: str | None = None
    # Lets a manager override the rate; falls back to the room type's base price.
    nightly_rate: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def _validate_range(self) -> "ReservationCreate":
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        if (self.check_out_date - self.check_in_date).days > 365:
            raise ValueError("A single stay cannot exceed 365 nights")
        return self


class ReservationUpdate(BaseModel):
    room_id: int | None = None
    check_in_date: date | None = None
    check_out_date: date | None = None
    adults: int | None = Field(None, ge=1, le=10)
    children: int | None = Field(None, ge=0, le=10)
    special_requests: str | None = None
    nightly_rate: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)


class ReservationCancel(BaseModel):
    reason: str | None = Field(None, max_length=255)


class PaymentSummary(ORMModel):
    id: int
    amount: Decimal
    method: str
    status: str
    paid_at: datetime | None


class ReservationRead(ORMModel):
    id: int
    reference: str
    status: ReservationStatus
    check_in_date: date
    check_out_date: date
    adults: int
    children: int
    nights: int
    nightly_rate: Decimal
    total_price: Decimal
    special_requests: str | None
    actual_check_in: datetime | None
    actual_check_out: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    guest: GuestSummary
    room: RoomRead


class ReservationWithBalance(ReservationRead):
    amount_paid: Decimal
    balance_due: Decimal


class QuickBookingCreate(BaseModel):
    """Walk-in flow: create the guest and the reservation in one request."""

    # Typed rather than a bare dict: an untyped payload skipped guest
    # validation entirely and surfaced bad input as a 500 instead of a 422.
    guest: GuestCreate
    room_id: int
    check_in_date: date
    check_out_date: date
    adults: int = Field(1, ge=1, le=10)
    children: int = Field(0, ge=0, le=10)
    special_requests: str | None = None
    nightly_rate: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
