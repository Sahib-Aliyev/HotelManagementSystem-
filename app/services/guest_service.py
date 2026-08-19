"""Guest registration and lookup."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.guest import Guest
from app.repositories.guest_repo import GuestRepository
from app.repositories.reservation_repo import ReservationRepository
from app.schemas.guest import GuestCreate, GuestUpdate

#: Guest fields that may legitimately be cleared. `full_name`, `phone`,
#: `document_type` and `document_number` are NOT NULL columns, so an explicit
#: null on those is a bad request, not an instruction.
NULLABLE_UPDATE_FIELDS = frozenset(
    {"email", "nationality", "date_of_birth", "address", "notes"}
)


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

        if "email" in data and data["email"]:
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
        _, reservation_count = await self.reservations.search(
            guest_id=guest_id, limit=1
        )
        if reservation_count:
            raise ConflictError(
                "This guest has reservation history and cannot be deleted. "
                "Their stays, payments and invoices would go with them.",
                details={"reservations": reservation_count},
            )
        await self.guests.delete(guest)
        await self.db.commit()

    async def history(self, guest_id: int):
        await self.get(guest_id)
        rows, _ = await self.reservations.search(guest_id=guest_id, limit=100)
        return rows
