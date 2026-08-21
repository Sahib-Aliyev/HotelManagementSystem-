---
paths:
  - "app/schemas/**"
  - "app/routers/api/**"
  - "app/routers/web.py"
---

# Schemas and endpoints

## Standing rules

- When adding a field to a form, check that it exists in the backend schema
  (`app/schemas/`) and in *every* creation path (e.g. both `ReservationCreate`
  and `QuickBookingCreate`). `nightly_rate` was lost exactly this way — see
  `docs/history/fixed-bugs.md`.
- **A schema field typed `X | None` is optional on input, not nullable.** An
  explicit JSON `null` survives `model_dump(exclude_unset=True)`, so the
  services drop `None` values before merging them (`NULLABLE_UPDATE_FIELDS` in
  `reservation_service.py` and `guest_service.py` list the fields that really
  can be cleared). Without that, `null` reaches the arithmetic or a NOT NULL
  column and becomes a 500.

## Lifted from the audits

- State does not travel in a query string. A manager's free-text justification
  and a financial decision belong in the request body: `RefundRequest`,
  `ReservationCheckOut`, `RoomStatusUpdate` →
  `docs/history/audit-2026-08-19-architecture.md`
