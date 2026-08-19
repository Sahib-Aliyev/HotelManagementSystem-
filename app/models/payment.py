"""Payments recorded against a reservation."""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal  # runtime import: SQLAlchemy resolves Mapped[] annotations
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.reservation import Reservation


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"
    ONLINE = "online"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    FAILED = "failed"


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount"),
        # A receipt number describes one movement of money, so it cannot appear
        # twice against the same stay. The service checks first for a readable
        # message; this is what holds under a concurrent double submit.
        UniqueConstraint(
            "reservation_id", "reference", name="uq_payment_reservation_reference"
        ),
        # Every revenue figure range-filters on paid_at, so without this each
        # dashboard load scanned the whole table.
        Index("ix_payments_paid_at", "paid_at"),
    )

    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, native_enum=False, length=20), nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, native_enum=False, length=20),
        default=PaymentStatus.PAID,
        nullable=False,
    )
    reference: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(String(255))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # A refund is a new row pointing at the settled payment it reverses; the
    # original is never edited, so the cash that came in stays on the record.
    refunded_payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"), index=True
    )
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    reservation: Mapped[Reservation] = relationship(back_populates="payments")
    refunded_payment: Mapped[Payment | None] = relationship(
        remote_side="Payment.id", foreign_keys=[refunded_payment_id]
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment {self.amount} {self.method.value}>"
