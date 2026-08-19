"""Reservation lifecycle: booking, modification, check-in, check-out, cancellation.

This module owns the rules that keep the calendar honest — above all, that a
room is never sold twice for the same night.
"""

import secrets
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import utcnow
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.models.reservation import Reservation, ReservationStatus
from app.models.room import RoomStatus
from app.models.user import User, UserRole
from app.repositories.guest_repo import GuestRepository
from app.repositories.reservation_repo import ReservationRepository
from app.repositories.room_repo import RoomRepository
from app.schemas.reservation import (
    ReservationCreate,
    ReservationUpdate,
    stay_range_error,
)
from app.services.pricing import accommodation_charge, total_due

#: Statuses from which a booking may still be edited.
EDITABLE_STATUSES = (ReservationStatus.PENDING, ReservationStatus.CONFIRMED)

#: PATCH fields that may legitimately be set back to null. Every other field
#: typed `X | None` is optional-on-input, not nullable — an explicit JSON null
#: there used to reach the arithmetic and raise a TypeError.
NULLABLE_UPDATE_FIELDS = frozenset({"special_requests"})


class ReservationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.reservations = ReservationRepository(db)
        self.rooms = RoomRepository(db)
        self.guests = GuestRepository(db)

    # --------------------------------------------------------------- helpers
    async def _generate_reference(self) -> str:
        """Human-readable, unique booking reference such as BK26-4F2A9C."""
        year = date.today().strftime("%y")
        for _ in range(10):
            candidate = f"BK{year}-{secrets.token_hex(3).upper()}"
            if await self.reservations.get_by_reference(candidate) is None:
                return candidate
        raise ConflictError("Could not allocate a booking reference. Please retry.")

    @staticmethod
    def _assert_is_manager(acting_user: User | None, action: str) -> None:
        """The one place this service decides what a receptionist may not do."""
        if acting_user is None or acting_user.role not in (
            UserRole.ADMIN,
            UserRole.MANAGER,
        ):
            raise PermissionDeniedError(f"Only a manager or administrator can {action}.")

    @classmethod
    def _assert_may_set_rate(
        cls, nightly_rate: Decimal | None, acting_user: User | None
    ) -> None:
        """Discounting is a manager decision, so it is enforced here.

        The booking form only shows the rate field to managers, but the field
        is just JSON on the way to the API — a receptionist can post any price
        they like unless the server says no. This is that check.
        """
        if nightly_rate is None:
            return
        cls._assert_is_manager(acting_user, "override the nightly rate")

    def _record_waiver(
        self, reservation: Reservation, amount: Decimal, acting_user: User | None
    ) -> None:
        """Write down money the hotel let go of, and who let go of it."""
        reservation.waived_amount = amount
        reservation.waived_at = utcnow()
        reservation.waived_by_id = acting_user.id if acting_user else None

    async def _assert_room_free(
        self,
        room_id: int,
        check_in: date,
        check_out: date,
        *,
        exclude_reservation_id: int | None = None,
    ) -> None:
        room = await self.rooms.get(room_id)
        if room is None:
            raise NotFoundError("Room not found.")
        if not room.is_bookable:
            raise ConflictError(
                f"Room {room.room_number} is out of service and cannot be booked."
            )
        free = await self.rooms.is_available(
            room_id, check_in, check_out, exclude_reservation_id=exclude_reservation_id
        )
        if not free:
            raise ConflictError(
                f"Room {room.room_number} is already booked for part of "
                f"{check_in.isoformat()} → {check_out.isoformat()}."
            )

    async def _commit_booking(self) -> None:
        """Commit a booking write, translating a lost race into a 409.

        `_assert_room_free` above reads and then this writes, which is
        time-of-check/time-of-use: two requests arriving together both read
        "free" and both insert. On PostgreSQL the `no_double_booking` exclusion
        constraint refuses the second one, and that arrives here as an
        `IntegrityError` — which is not an `AppError`, so without this it would
        bypass the exception handlers and answer 500. The check above still runs
        first because it produces the message a receptionist can act on; this is
        only the backstop for the interleaving it cannot see.

        `reference` is unique too, so a collision in `_generate_reference`
        surfaces the same way — the retry loop there checks by reading, which
        protects against the case that cannot happen rather than the one that
        can.
        """
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            detail = str(exc.orig) if exc.orig is not None else ""
            if "no_double_booking" in detail:
                raise ConflictError(
                    "That room was booked for part of these dates by someone "
                    "else a moment ago. Please pick another room or another date."
                ) from exc
            if "reference" in detail:
                raise ConflictError(
                    "Could not allocate a booking reference. Please retry."
                ) from exc
            raise

    # ----------------------------------------------------------------- reads
    async def get(self, reservation_id: int) -> Reservation:
        reservation = await self.reservations.get_full(reservation_id)
        if reservation is None:
            raise NotFoundError("Reservation not found.")
        return reservation

    async def get_by_reference(self, reference: str) -> Reservation:
        reservation = await self.reservations.get_by_reference(reference)
        if reservation is None:
            raise NotFoundError(f"No reservation with reference {reference}.")
        return reservation

    async def search(self, **kwargs) -> tuple[list[Reservation], int]:
        return await self.reservations.search(**kwargs)

    async def balance(self, reservation: Reservation) -> tuple[Decimal, Decimal]:
        """(amount_paid, balance_due) for a reservation, VAT included."""
        paid = await self.reservations.amount_paid(reservation.id)
        due = (total_due(reservation) - paid).quantize(Decimal("0.01"))
        return paid, due

    # -------------------------------------------------------------- creation
    async def create(
        self, payload: ReservationCreate, *, created_by: User | None = None
    ) -> Reservation:
        self._assert_may_set_rate(payload.nightly_rate, created_by)

        guest = await self.guests.get(payload.guest_id)
        if guest is None:
            raise NotFoundError("Guest not found.")

        if payload.check_in_date < date.today():
            raise ValidationError("Check-in date cannot be in the past.")

        room = await self.rooms.get(payload.room_id)
        if room is None:
            raise NotFoundError("Room not found.")

        occupancy = payload.adults + payload.children
        if occupancy > room.room_type.capacity:
            raise ValidationError(
                f"{room.room_type.name} sleeps {room.room_type.capacity}; "
                f"{occupancy} guests were requested."
            )

        await self._assert_room_free(
            payload.room_id, payload.check_in_date, payload.check_out_date
        )

        nights = (payload.check_out_date - payload.check_in_date).days
        nightly_rate = payload.nightly_rate or Decimal(room.room_type.base_price)

        reservation = await self.reservations.create(
            reference=await self._generate_reference(),
            guest_id=guest.id,
            room_id=room.id,
            created_by_id=created_by.id if created_by else None,
            check_in_date=payload.check_in_date,
            check_out_date=payload.check_out_date,
            adults=payload.adults,
            children=payload.children,
            status=ReservationStatus.CONFIRMED,
            nightly_rate=nightly_rate,
            total_price=accommodation_charge(nightly_rate, nights),
            special_requests=payload.special_requests,
        )
        await self._commit_booking()
        return await self.get(reservation.id)

    # ---------------------------------------------------------- modification
    async def update(
        self,
        reservation_id: int,
        payload: ReservationUpdate,
        *,
        acting_user: User | None = None,
    ) -> Reservation:
        self._assert_may_set_rate(payload.nightly_rate, acting_user)

        reservation = await self.get(reservation_id)
        if reservation.status not in EDITABLE_STATUSES:
            raise ConflictError(
                f"A {reservation.status.value.replace('_', ' ')} reservation "
                "can no longer be edited."
            )

        # An explicit `null` survives exclude_unset, so without this the merge
        # below reads None as "the new value" and the arithmetic blows up.
        data = {
            field: value
            for field, value in payload.model_dump(exclude_unset=True).items()
            if value is not None or field in NULLABLE_UPDATE_FIELDS
        }
        new_room_id = data.get("room_id", reservation.room_id)
        new_check_in = data.get("check_in_date", reservation.check_in_date)
        new_check_out = data.get("check_out_date", reservation.check_out_date)

        # The same range rule create applies, on the merged dates — PATCH used
        # to accept any range at all and re-price from it.
        problem = stay_range_error(new_check_in, new_check_out)
        if problem:
            raise ValidationError(problem)

        # Moving a stay into the past fabricates occupancy and ADR history.
        # Only a change is rejected: a booking that already started keeps its
        # arrival date when something else is edited.
        if new_check_in != reservation.check_in_date and new_check_in < date.today():
            raise ValidationError("Check-in date cannot be in the past.")

        dates_or_room_changed = (
            new_room_id != reservation.room_id
            or new_check_in != reservation.check_in_date
            or new_check_out != reservation.check_out_date
        )
        if dates_or_room_changed:
            await self._assert_room_free(
                new_room_id,
                new_check_in,
                new_check_out,
                exclude_reservation_id=reservation.id,
            )

        room = await self.rooms.get(new_room_id)
        adults = data.get("adults", reservation.adults)
        children = data.get("children", reservation.children)
        if adults + children > room.room_type.capacity:
            raise ValidationError(
                f"{room.room_type.name} sleeps {room.room_type.capacity}; "
                f"{adults + children} guests were requested."
            )

        room_changed = new_room_id != reservation.room_id

        for field, value in data.items():
            setattr(reservation, field, value)

        # A room change without an explicit rate override re-prices at the new
        # room type; otherwise the guest keeps the agreed rate.
        if room_changed and "nightly_rate" not in data:
            reservation.nightly_rate = Decimal(room.room_type.base_price)

        nights = (reservation.check_out_date - reservation.check_in_date).days
        reservation.total_price = accommodation_charge(reservation.nightly_rate, nights)

        await self._commit_booking()
        return await self.get(reservation.id)

    # ------------------------------------------------------------- lifecycle
    async def check_in(self, reservation_id: int) -> Reservation:
        reservation = await self.get(reservation_id)

        if reservation.status == ReservationStatus.CHECKED_IN:
            raise ConflictError("This guest is already checked in.")
        if reservation.status not in EDITABLE_STATUSES:
            raise ConflictError(
                f"Cannot check in a {reservation.status.value.replace('_', ' ')} "
                "reservation."
            )
        if reservation.check_in_date > date.today():
            raise ConflictError(
                f"This booking starts on {reservation.check_in_date.isoformat()}. "
                "Early check-in must be done by changing the dates first."
            )
        if reservation.room.status == RoomStatus.MAINTENANCE:
            raise ConflictError(
                f"Room {reservation.room.room_number} is out of service. "
                "Move the guest to another room first."
            )

        # Selling a room and occupying it are different questions, and the
        # calendar only answers the first. Overlap is defined with strict
        # comparisons so same-day turnover is sellable — correct — but that
        # means a stay ending today and a stay starting today are both legal,
        # and nothing here used to stop the arriving guest being checked into a
        # room the departing one has not left. That is how room 502 ended up
        # holding two simultaneous checked-in reservations; widening
        # `arrivals_on`/`departures_on` to `<=` only stopped the result being
        # invisible. The room has to be physically empty first.
        occupants = await self.reservations.active_for_room(reservation.room_id)
        if occupants:
            blocking = occupants[0]
            raise ConflictError(
                f"Room {reservation.room.room_number} is still occupied by "
                f"{blocking.guest.full_name} ({blocking.reference}), due out "
                f"{blocking.check_out_date.isoformat()}. Check them out first, "
                "or move this guest to another room.",
                details={"occupied_by": blocking.reference},
            )

        reservation.status = ReservationStatus.CHECKED_IN
        reservation.actual_check_in = utcnow()
        reservation.room.status = RoomStatus.OCCUPIED

        await self.db.commit()
        return await self.get(reservation.id)

    async def check_out(
        self,
        reservation_id: int,
        *,
        allow_outstanding_balance: bool = False,
        acting_user: User | None = None,
    ) -> Reservation:
        reservation = await self.get(reservation_id)

        if reservation.status != ReservationStatus.CHECKED_IN:
            raise ConflictError("Only a checked-in guest can be checked out.")

        _, balance_due = await self.balance(reservation)
        if balance_due > 0:
            if not allow_outstanding_balance:
                raise ConflictError(
                    f"There is an outstanding balance of {balance_due}. "
                    "Settle it or confirm check-out with a balance.",
                    details={"balance_due": str(balance_due)},
                )
            # Leaving without paying is a commercial decision, not a
            # front-desk convenience — so it needs a manager and it is
            # written down against the reservation.
            self._assert_is_manager(
                acting_user, "check a guest out with an outstanding balance"
            )
            self._record_waiver(reservation, balance_due, acting_user)

        reservation.status = ReservationStatus.CHECKED_OUT
        reservation.actual_check_out = utcnow()
        # The room is dirty, not immediately sellable.
        reservation.room.status = RoomStatus.CLEANING

        await self.db.commit()
        return await self.get(reservation.id)

    async def cancel(
        self,
        reservation_id: int,
        reason: str | None = None,
        *,
        waive_balance: bool = False,
        acting_user: User | None = None,
    ) -> Reservation:
        reservation = await self.get(reservation_id)

        if reservation.status == ReservationStatus.CANCELLED:
            raise ConflictError("This reservation is already cancelled.")
        if reservation.status == ReservationStatus.CHECKED_OUT:
            raise ConflictError("A completed stay cannot be cancelled.")

        was_in_house = reservation.status == ReservationStatus.CHECKED_IN
        if was_in_house:
            # Cancelling an in-house stay hides the nights slept from every
            # report and blocks any later payment, so the debt has to be dealt
            # with first and only a manager may write it off. A booking that
            # never arrived owes nothing and stays a front-desk action.
            self._assert_is_manager(acting_user, "cancel a stay that is checked in")
            _, balance_due = await self.balance(reservation)
            if balance_due > 0:
                if not waive_balance:
                    raise ConflictError(
                        f"This guest still owes {balance_due}. Take the payment, "
                        "or cancel with the balance explicitly written off.",
                        details={"balance_due": str(balance_due)},
                    )
                self._record_waiver(reservation, balance_due, acting_user)

        reservation.status = ReservationStatus.CANCELLED
        reservation.cancelled_at = utcnow()
        reservation.cancellation_reason = reason
        if was_in_house:
            reservation.room.status = RoomStatus.CLEANING

        await self.db.commit()
        return await self.get(reservation.id)

    async def mark_no_show(self, reservation_id: int) -> Reservation:
        reservation = await self.get(reservation_id)
        if reservation.status not in EDITABLE_STATUSES:
            raise ConflictError("Only a pending or confirmed booking can be a no-show.")
        if reservation.check_in_date > date.today():
            raise ConflictError("This booking has not reached its arrival date yet.")

        reservation.status = ReservationStatus.NO_SHOW
        await self.db.commit()
        return await self.get(reservation.id)

    # ------------------------------------------------------------ front desk
    async def front_desk(self) -> dict:
        today = date.today()
        return {
            "date": today,
            "arrivals": await self.reservations.arrivals_on(today),
            "departures": await self.reservations.departures_on(today),
            "in_house": await self.reservations.in_house(),
        }
