"""Importing this package registers every mapper with the declarative Base."""

from app.models.guest import DocumentType, Guest
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.reservation import (
    BLOCKING_STATUSES,
    Reservation,
    ReservationStatus,
)
from app.models.room import Room, RoomStatus, RoomType
from app.models.user import User, UserRole

__all__ = [
    "BLOCKING_STATUSES",
    "DocumentType",
    "Guest",
    "Invoice",
    "Payment",
    "PaymentMethod",
    "PaymentStatus",
    "Reservation",
    "ReservationStatus",
    "Room",
    "RoomStatus",
    "RoomType",
    "User",
    "UserRole",
]
