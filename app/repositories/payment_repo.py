"""Payment and invoice data access."""

from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.models.invoice import Invoice, InvoiceCounter
from app.models.payment import Payment, PaymentStatus
from app.repositories.base import BaseRepository


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC datetime range covering a calendar day."""
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = datetime.combine(day, time.max, tzinfo=UTC)
    return start, end


def is_cash_movement():
    """Rows that moved money: a settled payment, or a refund counter-entry.

    Refunds are append-only — the settled row keeps its PAID status and a new
    REFUNDED row points back at it — so anything summing money has to count
    both and give the refund a negative sign. Refunds recorded the old way (an
    edit in place, no `refunded_payment_id`) are neither, which is why the
    figures for historical data do not move.
    """
    return or_(
        Payment.status == PaymentStatus.PAID,
        and_(
            Payment.status == PaymentStatus.REFUNDED,
            Payment.refunded_payment_id.isnot(None),
        ),
    )


def signed_amount():
    """`amount`, negated for a refund counter-entry."""
    return case(
        (Payment.refunded_payment_id.isnot(None), -Payment.amount),
        else_=Payment.amount,
    )


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    async def list_for_reservation(self, reservation_id: int) -> list[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.reservation_id == reservation_id)
            .order_by(Payment.created_at)
        )
        return list((await self.db.execute(stmt)).scalars())

    async def get_refund_for(self, payment_id: int) -> Payment | None:
        """The counter-entry reversing a payment, if it has already been refunded."""
        stmt = select(Payment).where(Payment.refunded_payment_id == payment_id)
        return (await self.db.execute(stmt)).scalars().first()

    async def get_by_reference(
        self, reservation_id: int, reference: str
    ) -> Payment | None:
        """An existing movement of money carrying this receipt number."""
        stmt = select(Payment).where(
            Payment.reservation_id == reservation_id,
            Payment.reference == reference.strip(),
        )
        return (await self.db.execute(stmt)).scalars().first()

    async def revenue_between(self, start: date, end: date) -> Decimal:
        """Money taken in [start, end] inclusive, refunds deducted."""
        start_dt, _ = _day_bounds(start)
        _, end_dt = _day_bounds(end)
        stmt = select(func.coalesce(func.sum(signed_amount()), 0)).where(
            is_cash_movement(),
            Payment.paid_at >= start_dt,
            Payment.paid_at <= end_dt,
        )
        return Decimal(str((await self.db.execute(stmt)).scalar_one()))

    async def revenue_by_day(self, start: date, end: date) -> dict[date, Decimal]:
        start_dt, _ = _day_bounds(start)
        _, end_dt = _day_bounds(end)
        stmt = select(Payment.paid_at, signed_amount()).where(
            is_cash_movement(),
            Payment.paid_at >= start_dt,
            Payment.paid_at <= end_dt,
        )
        # Grouped in Python so the same code works on SQLite and PostgreSQL
        # without dialect-specific date truncation.
        totals: dict[date, Decimal] = {}
        for paid_at, amount in (await self.db.execute(stmt)).all():
            key = paid_at.date()
            totals[key] = totals.get(key, Decimal("0")) + Decimal(str(amount))
        return totals

    async def revenue_by_method(self, start: date, end: date) -> dict[str, Decimal]:
        start_dt, _ = _day_bounds(start)
        _, end_dt = _day_bounds(end)
        stmt = (
            select(Payment.method, func.coalesce(func.sum(signed_amount()), 0))
            .where(
                is_cash_movement(),
                Payment.paid_at >= start_dt,
                Payment.paid_at <= end_dt,
            )
            .group_by(Payment.method)
        )
        rows = (await self.db.execute(stmt)).all()
        return {method.value: Decimal(str(total)) for method, total in rows}


class InvoiceRepository(BaseRepository[Invoice]):
    model = Invoice

    async def get_by_reservation(self, reservation_id: int) -> Invoice | None:
        stmt = select(Invoice).where(Invoice.reservation_id == reservation_id)
        return (await self.db.execute(stmt)).unique().scalars().first()

    async def get_by_number(self, invoice_number: str) -> Invoice | None:
        stmt = select(Invoice).where(Invoice.invoice_number == invoice_number.upper())
        return (await self.db.execute(stmt)).unique().scalars().first()

    async def next_sequence(self, year: int) -> int:
        """Allocate the next invoice number for a year, atomically.

        This was `SELECT COUNT(*) + 1`, and a count is not a sequence. It goes
        backwards when a row is deleted — and `Invoice.reservation_id` cascades,
        so removing a reservation silently freed its number for reuse, which
        handed the same identity to two different tax documents. Two invoices
        issued concurrently also read the same count and collided on the unique
        index, surfacing as a 500.

        A counter row per year, incremented with `UPDATE … RETURNING`, is
        monotonic and safe under concurrency: the write locks the row, so the
        second caller waits and then reads the incremented value. Numbers are
        never reused, and a gap (an allocation whose transaction rolled back) is
        expected and harmless — a sequence guarantees uniqueness and order, not
        the absence of gaps.
        """
        stmt = (
            update(InvoiceCounter)
            .where(InvoiceCounter.year == year)
            .values(last_number=InvoiceCounter.last_number + 1)
            .returning(InvoiceCounter.last_number)
        )
        allocated = (await self.db.execute(stmt)).scalar_one_or_none()
        if allocated is None:
            # First invoice of this year. The unique index on `year` makes the
            # race safe: the loser's INSERT fails and it retries the UPDATE.
            #
            # Inside a SAVEPOINT, not a bare try/except. Catching the
            # `IntegrityError` and calling `db.rollback()` would discard the
            # caller's whole transaction — a repository has no business
            # unwinding work it cannot see. `begin_nested()` scopes the undo to
            # this one INSERT.
            try:
                async with self.db.begin_nested():
                    self.db.add(InvoiceCounter(year=year, last_number=1))
                    await self.db.flush()
                return 1
            except IntegrityError:
                allocated = (await self.db.execute(stmt)).scalar_one()
        return int(allocated)
