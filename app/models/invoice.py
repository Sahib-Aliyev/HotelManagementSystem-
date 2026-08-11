"""Invoices issued at check-out."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal  # runtime import: SQLAlchemy resolves Mapped[] annotations
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, utcnow

if TYPE_CHECKING:
    from app.models.reservation import Reservation


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    invoice_number: Mapped[str] = mapped_column(
        String(30), unique=True, index=True, nullable=False
    )
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    reservation: Mapped[Reservation] = relationship(
        back_populates="invoice", lazy="joined"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Invoice {self.invoice_number}>"
