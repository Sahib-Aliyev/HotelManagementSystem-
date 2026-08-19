"""Every amount of money the system derives, in one place.

`Reservation.total_price` is the accommodation charge only, net of tax. VAT is a
percentage of that, added on top. Both `ReservationService` and `PaymentService`
need the tax-inclusive figure to know what is actually owed, and `RoomService`
needs the accommodation charge to quote a price, so the arithmetic lives here
rather than in any of them — importing one service from another for a
calculation would create a circular import.

`accommodation_charge` used to be written out three separate times
(`ReservationService._price`, `PaymentService.folio`, `RoomService.find_available`).
The folio copy was the dangerous one: it derived the subtotal itself while
taking the total from `total_due`, so two independent sources described one bill
and the tax line silently absorbed any difference between them.
"""

from decimal import Decimal

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.reservation import Reservation

CENTS = Decimal("0.01")

#: Ceiling of Numeric(10, 2). PostgreSQL raises on overflow mid-transaction and
#: SQLite silently keeps the oversized value, so the price is checked before it
#: is ever stored.
MAX_TOTAL_PRICE = Decimal("99999999.99")


def accommodation_charge(nightly_rate: Decimal, nights: int) -> Decimal:
    """The room charge for a stay, net of tax."""
    total = (Decimal(nightly_rate) * nights).quantize(CENTS)
    if total > MAX_TOTAL_PRICE:
        raise ValidationError(
            f"The total price of {total} is above the maximum this system "
            f"can store ({MAX_TOTAL_PRICE}). Shorten the stay or lower the rate."
        )
    return total


def tax_on(subtotal: Decimal) -> Decimal:
    """VAT owed on a net amount."""
    return (Decimal(subtotal) * Decimal(str(settings.TAX_RATE))).quantize(CENTS)


def total_due(reservation: Reservation) -> Decimal:
    """The VAT-inclusive amount the guest owes for the whole stay."""
    subtotal = Decimal(reservation.total_price)
    return (subtotal + tax_on(subtotal)).quantize(CENTS)
