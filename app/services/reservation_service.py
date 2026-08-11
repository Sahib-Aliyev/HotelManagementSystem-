"""Reservation lifecycle: booking, modification, check-in, check-out, cancellation.

This module owns the rules that keep the calendar honest — above all, that a
room is never sold twice for the same night.
"""

import secrets
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import utcnow
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.reservation import Reservation, ReservationStatus
from app.models.room import RoomStatus
from app.models.user import User
from app.repositories.guest_repo import GuestRepository
from app.repositories.reservation_repo import ReservationRepository
from app.repositories.room_repo import RoomRepository
from app.schemas.reservation import ReservationCreate, ReservationUpdate

#: Statuses from which a booking may still be edited.
EDITABLE_STATUSES = (ReservationStatus.PENDING, ReservationStatus.CONFIRMED)


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
    def _price(nightly_rate: Decimal, nights: int) -> Decimal:
        return (Decimal(nightly_rate) * nights).quantize(Decimal("0.01"))

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
        """(amount_paid, balance_due) for a reservation."""
        paid = await self.reservations.amount_paid(reservation.id)
        due = (Decimal(reservation.total_price) - paid).quantize(Decimal("0.01"))
        return paid, due

    # -------------------------------------------------------------- creation
    async def create(
        self, payload: ReservationCreate, *, created_by: User | None = None
    ) -> Reservation:
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
            total_price=self._price(nightly_rate, nights),
            special_requests=payload.special_requests,
        )
        await self.db.commit()
        return await self.get(reservation.id)

    # ---------------------------------------------------------- modification
    async def update(
        self, reservation_id: int, payload: ReservationUpdate
    ) -> Reservation:
        reservation = await self.get(reservation_id)
        if reservation.status not in EDITABLE_STATUSES:
            raise ConflictError(
                f"A {reservation.status.value.replace('_', ' ')} reservation "
                "can no longer be edited."
            )

        data = payload.model_dump(exclude_unset=True)
        new_room_id = data.get("room_id", reservation.room_id)
        new_check_in = data.get("check_in_date", reservation.check_in_date)
        new_check_out = data.get("check_out_date", reservation.check_out_date)

        if new_check_out <= new_check_in:
            raise ValidationError("Check-out must be after check-in.")

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
        reservation.total_price = self._price(reservation.nightly_rate, nights)

        await self.db.commit()
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

        reservation.status = ReservationStatus.CHECKED_IN
        reservation.actual_check_in = utcnow()
        reservation.room.status = RoomStatus.OCCUPIED

        await self.db.commit()
        return await self.get(reservation.id)

    async def check_out(
        self, reservation_id: int, *, allow_outstanding_balance: bool = False
    ) -> Reservation:
        reservation = await self.get(reservation_id)

        if reservation.status != ReservationStatus.CHECKED_IN:
            raise ConflictError("Only a checked-in guest can be checked out.")

        _, balance_due = await self.balance(reservation)
        if balance_due > 0 and not allow_outstanding_balance:
            raise ConflictError(
                f"There is an outstanding balance of {balance_due}. "
                "Settle it or confirm check-out with a balance.",
                details={"balance_due": str(balance_due)},
            )

        reservation.status = ReservationStatus.CHECKED_OUT
        reservation.actual_check_out = utcnow()
        # The room is dirty, not immediately sellable.
        reservation.room.status = RoomStatus.CLEANING

        await self.db.commit()
        return await self.get(reservation.id)

    async def cancel(self, reservation_id: int, reason: str | None = None) -> Reservation:
        reservation = await self.get(reservation_id)

        if reservation.status == ReservationStatus.CANCELLED:
            raise ConflictError("This reservation is already cancelled.")
        if reservation.status == ReservationStatus.CHECKED_OUT:
            raise ConflictError("A completed stay cannot be cancelled.")

        was_in_house = reservation.status == ReservationStatus.CHECKED_IN

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
