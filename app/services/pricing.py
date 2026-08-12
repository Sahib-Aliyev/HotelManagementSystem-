"""VAT-inclusive amount owed for a stay.

`Reservation.total_price` is the accommodation charge only, net of tax — it is
what `ReservationService._price()` sets at booking time. VAT is a percentage
of that, added on top. Both `ReservationService` and `PaymentService` need the
tax-inclusive figure to know what is actually owed, so it lives here rather
than in either — importing one service from the other for a single
calculation would create a circular import.
"""

from decimal import Decimal

from app.core.config import settings
from app.models.reservation import Reservation

CENTS = Decimal("0.01")


def total_due(reservation: Reservation) -> Decimal:
    """The VAT-inclusive amount the guest owes for the whole stay."""
    subtotal = Decimal(reservation.total_price)
    tax = (subtotal * Decimal(str(settings.TAX_RATE))).quantize(CENTS)
    return (subtotal + tax).quantize(CENTS)
