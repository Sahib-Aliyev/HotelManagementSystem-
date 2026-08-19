"""Reservations — the centre of the booking domain."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal  # runtime import: SQLAlchemy resolves Mapped[] annotations
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.guest import Guest
    from app.models.invoice import Invoice
    from app.models.payment import Payment
    from app.models.room import Room
    from app.models.user import User


class ReservationStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


#: Statuses that occupy a room on the calendar and therefore block other bookings.
BLOCKING_STATUSES = (
    ReservationStatus.PENDING,
    ReservationStatus.CONFIRMED,
    ReservationStatus.CHECKED_IN,
)


class Reservation(Base, TimestampMixin):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("check_out_date > check_in_date", name="ck_reservation_dates"),
        CheckConstraint("adults >= 1", name="ck_reservation_adults"),
    )

    reference: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    guest_id: Mapped[int] = mapped_column(
        ForeignKey("guests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    check_in_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_out_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    adults: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    children: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[ReservationStatus] = mapped_column(
        SAEnum(ReservationStatus, native_enum=False, length=20),
        default=ReservationStatus.CONFIRMED,
        nullable=False,
        index=True,
    )
    nightly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    special_requests: Mapped[str | None] = mapped_column(Text)

    actual_check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(255))

    # Money let go of: check-out with an outstanding balance, or cancelling a
    # stay that was already in house. Both are manager decisions and both used
    # to leave no trace of who took them.
    waived_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    waived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    waived_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    guest: Mapped[Guest] = relationship(back_populates="reservations", lazy="joined")
    room: Mapped[Room] = relationship(back_populates="reservations", lazy="joined")
    created_by: Mapped[User | None] = relationship(
        back_populates="created_reservations", foreign_keys=[created_by_id]
    )
    waived_by: Mapped[User | None] = relationship(foreign_keys=[waived_by_id])
    payments: Mapped[list[Payment]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan"
    )
    invoice: Mapped[Invoice | None] = relationship(
        back_populates="reservation", cascade="all, delete-orphan", uselist=False
    )

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days

    @property
    def guest_count(self) -> int:
        return self.adults + self.children

    @property
    def is_active(self) -> bool:
        return self.status in BLOCKING_STATUSES

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reservation {self.reference} {self.status.value}>"
