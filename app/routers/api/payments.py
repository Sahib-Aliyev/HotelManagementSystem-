"""Payment, folio and invoice endpoints."""

from fastapi import APIRouter, status
from fastapi.responses import Response

from app.core.deps import DbSession, ManagerUser, StaffUser
from app.schemas.payment import Folio, InvoiceRead, PaymentCreate, PaymentRead
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def record_payment(payload: PaymentCreate, db: DbSession, _user: StaffUser):
    return await PaymentService(db).record(payload)


@router.get("/reservation/{reservation_id}", response_model=list[PaymentRead])
async def payments_for_reservation(
    reservation_id: int, db: DbSession, _user: StaffUser
):
    return await PaymentService(db).list_for_reservation(reservation_id)


@router.get("/folio/{reservation_id}", response_model=Folio)
async def folio(reservation_id: int, db: DbSession, _user: StaffUser):
    return await PaymentService(db).folio(reservation_id)


@router.post("/{payment_id}/refund", response_model=PaymentRead)
async def refund(
    payment_id: int, db: DbSession, _manager: ManagerUser, note: str | None = None
):
    return await PaymentService(db).refund(payment_id, note)


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
