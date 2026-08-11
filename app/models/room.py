"""Room types and physical rooms."""

from __future__ import annotations

import enum
from decimal import Decimal  # runtime import: SQLAlchemy resolves Mapped[] annotations
from typing import TYPE_CHECKING

from sqlalchemy import (
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.reservation import Reservation


class RoomStatus(str, enum.Enum):
    """Housekeeping / physical state — distinct from whether a room is booked."""

    AVAILABLE = "available"
    OCCUPIED = "occupied"
    CLEANING = "cleaning"
    MAINTENANCE = "maintenance"


class RoomType(Base, TimestampMixin):
    __tablename__ = "room_types"

    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    amenities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    rooms: Mapped[list[Room]] = relationship(
        back_populates="room_type", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RoomType {self.name}>"


class Room(Base, TimestampMixin):
    __tablename__ = "rooms"

    room_number: Mapped[str] = mapped_column(
        String(10), unique=True, index=True, nullable=False
    )
    room_type_id: Mapped[int] = mapped_column(
        ForeignKey("room_types.id", ondelete="CASCADE"), nullable=False
    )
    floor: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[RoomStatus] = mapped_column(
        SAEnum(RoomStatus, native_enum=False, length=20),
        default=RoomStatus.AVAILABLE,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    room_type: Mapped[RoomType] = relationship(back_populates="rooms", lazy="joined")
    reservations: Mapped[list[Reservation]] = relationship(back_populates="room")

    @property
    def is_bookable(self) -> bool:
        """A room under maintenance can never be sold, whatever the calendar says."""
        return self.status != RoomStatus.MAINTENANCE

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Room {self.room_number}>"
