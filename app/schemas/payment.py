"""Payment and invoice schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.payment import PaymentMethod, PaymentStatus
from app.schemas.common import ORMModel


class PaymentCreate(BaseModel):
    reservation_id: int
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    method: PaymentMethod
    status: PaymentStatus = PaymentStatus.PAID
    reference: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=255)


class PaymentRead(ORMModel):
    id: int
    reservation_id: int
    amount: Decimal
    method: PaymentMethod
    status: PaymentStatus
    reference: str | None
    note: str | None
    paid_at: datetime | None
    created_at: datetime


class InvoiceRead(ORMModel):
    id: int
    invoice_number: str
    reservation_id: int
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    issued_at: datetime


class FolioLine(BaseModel):
    label: str
    detail: str
    amount: Decimal


class Folio(BaseModel):
    """The full financial picture for one reservation."""

    reservation_reference: str
    guest_name: str
    room_number: str
    lines: list[FolioLine]
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
