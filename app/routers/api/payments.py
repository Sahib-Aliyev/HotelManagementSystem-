"""Payment, folio and invoice endpoints."""

from fastapi import APIRouter, status
from fastapi.responses import Response

from app.core.deps import DbSession, ManagerUser, StaffUser
from app.schemas.payment import (
    Folio,
    InvoiceRead,
    PaymentCreate,
    PaymentRead,
    RefundRequest,
)
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def record_payment(payload: PaymentCreate, db: DbSession, user: StaffUser):
    return await PaymentService(db).record(payload, acting_user=user)


@router.get("/reservation/{reservation_id}", response_model=list[PaymentRead])
async def payments_for_reservation(reservation_id: int, db: DbSession, _user: StaffUser):
    return await PaymentService(db).list_for_reservation(reservation_id)


@router.get("/folio/{reservation_id}", response_model=Folio)
async def folio(reservation_id: int, db: DbSession, _user: StaffUser):
    return await PaymentService(db).folio(reservation_id)


@router.post("/{payment_id}/refund", response_model=PaymentRead)
async def refund(
    payment_id: int,
    db: DbSession,
    manager: ManagerUser,
    payload: RefundRequest | None = None,
):
    """Returns the refund counter-entry; the settled payment it reverses is
    left untouched.

    The note travels in the body. As a query parameter a manager's free-text
    justification ended up in every access log and proxy history along the way.
    """
    return await PaymentService(db).refund(
        payment_id, payload.note if payload else None, acting_user=manager
    )


# ------------------------------------------------------------------ invoices
invoices_router = APIRouter(prefix="/invoices", tags=["Invoices"])


@invoices_router.post(
    "/reservation/{reservation_id}",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
async def issue_invoice(reservation_id: int, db: DbSession, _user: StaffUser):
    """Idempotent — returns the existing invoice if one was already issued."""
    return await InvoiceService(db).issue(reservation_id)


@invoices_router.get("/reservation/{reservation_id}", response_model=InvoiceRead)
async def get_invoice(reservation_id: int, db: DbSession, _user: StaffUser):
    return await InvoiceService(db).get_for_reservation(reservation_id)


@invoices_router.get("/reservation/{reservation_id}/pdf")
async def download_invoice_pdf(reservation_id: int, db: DbSession, _user: StaffUser):
    pdf_bytes, filename = await InvoiceService(db).render_pdf(reservation_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
