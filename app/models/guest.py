"""Hotel guests."""

from __future__ import annotations

import enum
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum as SAEnum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.reservation import Reservation


class DocumentType(str, enum.Enum):
    PASSPORT = "passport"
    ID_CARD = "id_card"
    DRIVER_LICENSE = "driver_license"


class Guest(Base, TimestampMixin):
    __tablename__ = "guests"
    # The same document number may legitimately repeat across document types,
    # so uniqueness is on the pair.
    __table_args__ = (
        UniqueConstraint("document_type", "document_number", name="uq_guest_document"),
    )

    full_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    document_type: Mapped[DocumentType] = mapped_column(
        SAEnum(DocumentType, native_enum=False, length=20),
        default=DocumentType.PASSPORT,
        nullable=False,
    )
    document_number: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    nationality: Mapped[str | None] = mapped_column(String(60))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    address: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    reservations: Mapped[list[Reservation]] = relationship(
        back_populates="guest", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Guest {self.full_name}>"
