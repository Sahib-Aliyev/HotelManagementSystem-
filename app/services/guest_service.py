"""Guest registration and lookup."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.guest import Guest
from app.models.reservation import ReservationStatus
from app.repositories.guest_repo import GuestRepository
from app.repositories.reservation_repo import ReservationRepository
from app.schemas.guest import GuestCreate, GuestUpdate

#: Guest fields that may legitimately be cleared. `full_name`, `phone`,
#: `document_type` and `document_number` are NOT NULL columns, so an explicit
#: null on those is a bad request, not an instruction.
NULLABLE_UPDATE_FIELDS = frozenset(
    {"email", "nationality", "date_of_birth", "address", "notes"}
)

#: Placeholders left behind by `anonymise()`. `full_name` doubles as the marker
#: that a record has already been erased, so it must not look like a real name.
ANONYMISED_NAME = "[erased guest]"
ANONYMISED_PHONE = "[erased]"


class GuestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.guests = GuestRepository(db)
        self.reservations = ReservationRepository(db)

    async def get(self, guest_id: int) -> Guest:
        guest = await self.guests.get(guest_id)
        if guest is None:
            raise NotFoundError("Guest not found.")
        return guest

    async def search(
        self, term: str | None = None, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[Guest], int]:
        return await self.guests.search(term, limit=limit, offset=offset)

    async def create(self, payload: GuestCreate) -> Guest:
        existing = await self.guests.get_by_document(
            payload.document_type, payload.document_number
        )
        if existing is not None:
            raise ConflictError(
                f"{existing.full_name} is already registered with this document.",
                details={"guest_id": existing.id},
            )
        guest = await self.guests.create(
            full_name=payload.full_name.strip(),
            phone=payload.phone.strip(),
            email=payload.email.strip().lower() if payload.email else None,
            document_type=payload.document_type,
            document_number=payload.document_number,
            nationality=payload.nationality,
            date_of_birth=payload.date_of_birth,
            address=payload.address,
            notes=payload.notes,
        )
        await self.db.commit()
        return guest

    async def get_or_create(self, payload: GuestCreate) -> Guest:
        """Used by the walk-in flow — reuse a returning guest's record."""
        existing = await self.guests.get_by_document(
            payload.document_type, payload.document_number
        )
        if existing is not None:
            return existing
        return await self.create(payload)

    async def update(self, guest_id: int, payload: GuestUpdate) -> Guest:
        guest = await self.get(guest_id)
        # An explicit `null` on a required column would otherwise be written
        # straight through and fail as a 500 in the database, not a 422.
        data = {
            field: value
            for field, value in payload.model_dump(exclude_unset=True).items()
            if value is not None or field in NULLABLE_UPDATE_FIELDS
        }

        new_type = data.get("document_type", guest.document_type)
        new_number = data.get("document_number")
        if new_number is not None:
            new_number = new_number.replace(" ", "").upper()
            data["document_number"] = new_number
            clash = await self.guests.get_by_document(
                new_type, new_number, exclude_id=guest_id
            )
            if clash is not None:
                raise ConflictError("Another guest already uses this document number.")

        if data.get("email"):
            data["email"] = data["email"].strip().lower()

        for field, value in data.items():
            setattr(guest, field, value)

        await self.db.commit()
        await self.db.refresh(guest)
        return guest

    async def delete(self, guest_id: int) -> None:
        """Delete a guest who has never had a reservation.

        Two problems used to live in these five lines. `Guest.reservations` is
        lazy-loaded, so touching it here raised MissingGreenlet — not an
        AppError, so the endpoint answered 500 every time. And the guard only
        looked at *active* stays, while the relationship cascades to payments
        and invoices: deleting a guest with a completed stay would have wiped
        their financial history in one request. Reservations are counted
        through the repository now, and any reservation at all blocks the
        delete.
        """
        guest = await self.get(guest_id)
        _, reservation_count = await self.reservations.search(guest_id=guest_id, limit=1)
        if reservation_count:
            raise ConflictError(
                "This guest has reservation history and cannot be deleted. "
                "Their stays, payments and invoices would go with them.",
                details={"reservations": reservation_count},
            )
        await self.guests.delete(guest)
        await self.db.commit()

    async def anonymise(self, guest_id: int) -> Guest:
        """Erase a guest's personal data while keeping their stays and money.

        `delete()` above refuses anybody who has ever had a reservation, which is
        right — the relationship cascades to payments and invoices, so deleting
        would take the financial record with it. But it also meant erasure was
        impossible for exactly the guests who have data worth erasing, and
        nothing here ever expired a passport number.

        So the personal data goes and the ledger stays: contact fields are
        cleared, the name becomes a tombstone, and the document number is
        replaced with a unique placeholder because the column is NOT NULL and
        unique on `(document_type, document_number)`. Reservations, payments and
        invoices keep pointing at the same row, so occupancy, revenue and the
        VAT record are untouched.

        Irreversible on purpose. A guest still in the hotel is refused: erasing
        someone mid-stay would leave the front desk unable to identify the
        occupant of a room.
        """
        guest = await self.get(guest_id)
        if guest.full_name == ANONYMISED_NAME:
            raise ConflictError("This guest record has already been anonymised.")

        active, _ = await self.reservations.search(
            guest_id=guest_id, status=ReservationStatus.CHECKED_IN, limit=1
        )
        if active:
            raise ConflictError(
                "This guest is currently checked in. Check them out before "
                "erasing their personal data."
            )

        guest.full_name = ANONYMISED_NAME
        guest.phone = ANONYMISED_PHONE
        guest.document_number = f"ERASED-{guest.id}"
        guest.email = None
        guest.nationality = None
        guest.date_of_birth = None
        guest.address = None
        guest.notes = f"Personal data erased on {date.today().isoformat()}."

        await self.db.commit()
        await self.db.refresh(guest)
        return guest

    async def history(self, guest_id: int):
        await self.get(guest_id)
        rows, _ = await self.reservations.search(guest_id=guest_id, limit=100)
        return rows
