"""Reservation schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.reservation import ReservationStatus
from app.schemas.common import ORMModel
from app.schemas.guest import GuestCreate, GuestSummary
from app.schemas.room import RoomRead

#: A stay longer than this is a data-entry error, not a booking. Left
#: unchecked on PATCH it also took the room off sale until the year 9999 and
#: overflowed Numeric(10, 2) when the price was recomputed.
MAX_STAY_NIGHTS = 365


def stay_range_error(check_in: date, check_out: date) -> str | None:
    """The shared date rule. Returns a message, or None when the range is fine.

    `create` validates it in the schema and `update` on the merged result, so
    the rule has to live somewhere both can reach.
    """
    if check_out <= check_in:
        return "check_out_date must be after check_in_date"
    if (check_out - check_in).days > MAX_STAY_NIGHTS:
        return f"A single stay cannot exceed {MAX_STAY_NIGHTS} nights"
    return None


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
        problem = stay_range_error(self.check_in_date, self.check_out_date)
        if problem:
            raise ValueError(problem)
        return self


class ReservationUpdate(BaseModel):
    room_id: int | None = None
    check_in_date: date | None = None
    check_out_date: date | None = None
    adults: int | None = Field(None, ge=1, le=10)
    children: int | None = Field(None, ge=0, le=10)
    special_requests: str | None = None
    nightly_rate: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def _validate_range(self) -> "ReservationUpdate":
        # Only checkable here when both dates arrive together; a one-sided
        # change is validated against the stored value in the service.
        if self.check_in_date and self.check_out_date:
            problem = stay_range_error(self.check_in_date, self.check_out_date)
            if problem:
                raise ValueError(problem)
        return self


class ReservationCancel(BaseModel):
    reason: str | None = Field(None, max_length=255)
    #: Cancelling an in-house stay with money still owed writes the debt off,
    #: so it has to be asked for explicitly and only a manager may do it.
    waive_balance: bool = False


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
    waived_amount: Decimal | None
    waived_at: datetime | None
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

    @model_validator(mode="after")
    def _validate_range(self) -> "QuickBookingCreate":
        # Without this the router builds a ReservationCreate from the payload
        # and pydantic raises inside the handler — a 500 where the client
        # should have been told 422.
        problem = stay_range_error(self.check_in_date, self.check_out_date)
        if problem:
            raise ValueError(problem)
        return self
