"""Recording payments and building the guest folio."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import utcnow
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.payment import Payment, PaymentStatus
from app.models.reservation import ReservationStatus
from app.models.user import User
from app.repositories.payment_repo import PaymentRepository
from app.repositories.reservation_repo import ReservationRepository
from app.schemas.payment import Folio, FolioLine, PaymentCreate
from app.services.pricing import total_due

CENTS = Decimal("0.01")


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.payments = PaymentRepository(db)
        self.reservations = ReservationRepository(db)

    async def list_for_reservation(self, reservation_id: int) -> list[Payment]:
        return await self.payments.list_for_reservation(reservation_id)

    async def record(
        self, payload: PaymentCreate, *, acting_user: User | None = None
    ) -> Payment:
        reservation = await self.reservations.get_full(payload.reservation_id)
        if reservation is None:
            raise NotFoundError("Reservation not found.")
        if reservation.status == ReservationStatus.CANCELLED:
            raise ConflictError("Cannot take payment on a cancelled reservation.")

        paid = await self.reservations.amount_paid(reservation.id)
        outstanding = (total_due(reservation) - paid).quantize(CENTS)
        # The ceiling applies whatever the status: `status` is client-settable,
        # so gating it on PAID let any amount through as "pending" and only
        # Numeric(10, 2) overflow stopped it.
        if payload.amount > outstanding:
            raise ValidationError(
                f"Payment of {payload.amount} exceeds the outstanding balance "
                f"of {outstanding}.",
                details={"outstanding": str(outstanding)},
            )

        payment = await self.payments.create(
            reservation_id=reservation.id,
            amount=payload.amount,
            method=payload.method,
            status=payload.status,
            reference=payload.reference,
            note=payload.note,
            paid_at=utcnow() if payload.status == PaymentStatus.PAID else None,
            recorded_by_id=acting_user.id if acting_user else None,
        )
        await self.db.commit()
        return payment

    async def refund(
        self,
        payment_id: int,
        note: str | None = None,
        *,
        acting_user: User | None = None,
    ) -> Payment:
        """Reverse a settled payment by writing a counter-entry.

        The settled row is left exactly as it was. Editing it in place used to
        erase the amount, the original note and any trace that a refund had
        happened at all, so a cash payment could be taken and then made to look
        as though the guest had never paid.
        """
        payment = await self.payments.get(payment_id)
        if payment is None:
            raise NotFoundError("Payment not found.")
        if payment.status != PaymentStatus.PAID:
            raise ConflictError("Only a settled payment can be refunded.")
        if await self.payments.get_refund_for(payment.id) is not None:
            raise ConflictError("This payment has already been refunded.")

        refund = await self.payments.create(
            reservation_id=payment.reservation_id,
            amount=payment.amount,
            method=payment.method,
            status=PaymentStatus.REFUNDED,
            reference=payment.reference,
            note=note,
            paid_at=utcnow(),
            refunded_payment_id=payment.id,
            recorded_by_id=acting_user.id if acting_user else None,
        )
        await self.db.commit()
        return refund

    async def folio(self, reservation_id: int) -> Folio:
        """The itemised bill for a stay."""
        reservation = await self.reservations.get_full(reservation_id)
        if reservation is None:
            raise NotFoundError("Reservation not found.")

        nights = reservation.nights
        rate = Decimal(reservation.nightly_rate)
        accommodation = (rate * nights).quantize(CENTS)

        lines = [
            FolioLine(
                label=f"{reservation.room.room_type.name} — Room {reservation.room.room_number}",
                detail=f"{nights} night{'s' if nights != 1 else ''} × {rate} {settings.CURRENCY}",
                amount=accommodation,
            )
        ]

        subtotal = accommodation
        total = total_due(reservation)
        tax_amount = (total - subtotal).quantize(CENTS)

        # total_price is stored net of tax; VAT is added on top and owed
        # along with it — the balance below is what check-out checks too.
        paid = await self.reservations.amount_paid(reservation.id)
        balance = (total - paid).quantize(CENTS)

        return Folio(
            reservation_reference=reservation.reference,
            guest_name=reservation.guest.full_name,
            room_number=reservation.room.room_number,
            lines=lines,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total=total,
            amount_paid=paid,
            balance_due=balance,
        )
