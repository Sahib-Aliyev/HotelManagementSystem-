"""Invoice issuing and PDF rendering."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.invoice import Invoice
from app.models.reservation import ReservationStatus
from app.repositories.payment_repo import InvoiceRepository
from app.repositories.reservation_repo import ReservationRepository
from app.services.payment_service import PaymentService

CENTS = Decimal("0.01")
BRAND = colors.HexColor("#1E3A8A")


def _esc(value: object) -> str:
    """Make a value safe to interpolate into a Paragraph.

    Paragraph parses its text as mini-XML, so a guest named "<b>Ali" raised a
    parse error and took the whole invoice down with a 500 — permanently, for
    that guest. Table cells below take plain strings and are not parsed, so
    only Paragraph content needs this.
    """
    return escape("" if value is None else str(value))
ACCENT = colors.HexColor("#10B981")
MUTED = colors.HexColor("#64748B")


class InvoiceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.invoices = InvoiceRepository(db)
        self.reservations = ReservationRepository(db)
        self.payments = PaymentService(db)

    async def _next_number(self) -> str:
        seq = await self.invoices.next_sequence()
        return f"INV-{date.today().year}-{seq:05d}"

    async def issue(self, reservation_id: int) -> Invoice:
        reservation = await self.reservations.get_full(reservation_id)
        if reservation is None:
            raise NotFoundError("Reservation not found.")
        if reservation.status == ReservationStatus.CANCELLED:
            raise ConflictError("Cannot invoice a cancelled reservation.")

        existing = await self.invoices.get_by_reservation(reservation_id)
        if existing is not None:
            return existing

        folio = await self.payments.folio(reservation_id)
        invoice = await self.invoices.create(
            invoice_number=await self._next_number(),
            reservation_id=reservation_id,
            subtotal=folio.subtotal,
            tax_amount=folio.tax_amount,
            total_amount=folio.total,
        )
        await self.db.commit()
        return invoice

    async def get_for_reservation(self, reservation_id: int) -> Invoice:
        invoice = await self.invoices.get_by_reservation(reservation_id)
        if invoice is None:
            raise NotFoundError("No invoice has been issued for this reservation.")
        return invoice

    async def render_pdf(self, reservation_id: int) -> tuple[bytes, str]:
        """Render an already-issued invoice. Returns (pdf_bytes, filename).

        Read-only on purpose. This used to call `issue()`, so a GET wrote a row
        and consumed an invoice number — and because the session cookie is
        samesite=lax, a link mailed to a staff member was enough to trigger it.
        Issuing stays behind the explicit POST.
        """
        invoice = await self.get_for_reservation(reservation_id)
        reservation = await self.reservations.get_full(reservation_id)
        folio = await self.payments.folio(reservation_id)

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=f"Invoice {invoice.invoice_number}",
        )

        styles = getSampleStyleSheet()
        h1 = ParagraphStyle(
            "h1", parent=styles["Heading1"], textColor=BRAND, fontSize=20, spaceAfter=2
        )
        small = ParagraphStyle(
            "small", parent=styles["Normal"], textColor=MUTED, fontSize=9
        )
        label = ParagraphStyle(
            "label", parent=styles["Normal"], textColor=MUTED, fontSize=8, spaceAfter=1
        )
        value = ParagraphStyle("value", parent=styles["Normal"], fontSize=10)

        story = [
            Paragraph(_esc(settings.APP_NAME), h1),
            Paragraph("Baku, Azerbaijan · +994 12 000 00 00 · stay@grandaurora.az", small),
            Spacer(1, 10 * mm),
        ]

        meta = Table(
            [
                [
                    Paragraph("INVOICE NUMBER", label),
                    Paragraph("ISSUE DATE", label),
                    Paragraph("BOOKING REFERENCE", label),
                ],
                [
                    Paragraph(_esc(invoice.invoice_number), value),
                    Paragraph(invoice.issued_at.strftime("%d %b %Y"), value),
                    Paragraph(_esc(reservation.reference), value),
                ],
            ],
            colWidths=[57 * mm, 57 * mm, 56 * mm],
        )
        meta.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                    ("LINEBELOW", (0, 1), (-1, 1), 0.5, colors.HexColor("#E2E8F0")),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                ]
            )
        )
        story += [meta, Spacer(1, 8 * mm)]

        guest_block = Table(
            [
                [Paragraph("BILLED TO", label), Paragraph("STAY DETAILS", label)],
                [
                    Paragraph(
                        f"{_esc(reservation.guest.full_name)}<br/>"
                        f"{_esc(reservation.guest.phone)}<br/>"
                        f"{_esc(reservation.guest.email)}",
                        value,
                    ),
                    Paragraph(
                        f"Room {_esc(reservation.room.room_number)} · "
                        f"{_esc(reservation.room.room_type.name)}<br/>"
                        f"{reservation.check_in_date.strftime('%d %b %Y')} → "
                        f"{reservation.check_out_date.strftime('%d %b %Y')}<br/>"
                        f"{reservation.nights} night(s) · {reservation.guest_count} guest(s)",
                        value,
                    ),
                ],
            ],
            colWidths=[85 * mm, 85 * mm],
        )
        guest_block.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [guest_block, Spacer(1, 10 * mm)]

        currency = settings.CURRENCY
        rows = [["Description", "Details", f"Amount ({currency})"]]
        for line in folio.lines:
            rows.append([line.label, line.detail, f"{line.amount:,.2f}"])

        rows += [
            ["", "Subtotal", f"{folio.subtotal:,.2f}"],
            ["", f"VAT ({settings.TAX_RATE:.0%})", f"{folio.tax_amount:,.2f}"],
            ["", "Total", f"{folio.total:,.2f}"],
            ["", "Paid", f"-{folio.amount_paid:,.2f}"],
            ["", "Balance due", f"{folio.balance_due:,.2f}"],
        ]

        items = Table(rows, colWidths=[70 * mm, 60 * mm, 40 * mm])
        last = len(rows) - 1
        items.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 1), (-1, -6), 0.4, colors.HexColor("#E2E8F0")),
                    ("LINEABOVE", (1, last - 4), (-1, last - 4), 0.5, MUTED),
                    ("FONTNAME", (1, last - 2), (-1, last - 2), "Helvetica-Bold"),
                    ("FONTNAME", (1, last), (-1, last), "Helvetica-Bold"),
                    ("TEXTCOLOR", (1, last), (-1, last), ACCENT if folio.balance_due <= 0 else colors.HexColor("#DC2626")),
                    ("LINEABOVE", (1, last), (-1, last), 0.5, MUTED),
                ]
            )
        )
        story += [items, Spacer(1, 12 * mm)]

        story += [
            Paragraph(
                "Thank you for staying with us. This invoice was generated "
                "electronically and is valid without a signature.",
                small,
            )
        ]

        doc.build(story)
        filename = f"{invoice.invoice_number}.pdf"
        return buffer.getvalue(), filename
