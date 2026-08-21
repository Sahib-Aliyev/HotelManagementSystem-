---
paths:
  - "app/services/**"
  - "app/core/security.py"
---

# Service-layer runtime

- bcrypt and ReportLab are synchronous and CPU-bound, so they run through
  `starlette.concurrency.run_in_threadpool`. `AuthService` calls
  `hash_password_async`, `verify_password_async` and
  `waste_password_time_async`; the sync versions are for non-request callers
  such as `seed.py`. On the event loop they stalled the whole process,
  `/health` included → `docs/history/audit-2026-08-19-architecture.md`
- `GuestService.anonymise()` is the erasure path: it clears the contact fields,
  tombstones the name and writes a per-id placeholder document number while the
  reservations, payments and invoices keep pointing at the same row, so no
  reported figure moves. Manager-only, irreversible, and refused while the guest
  is still in the hotel → `docs/history/audit-2026-08-19-architecture.md`
- The role belongs to the state change, not to the route:
  `RoomService._assert_may_take_out_of_service`, the same reasoning as
  `ReservationService._assert_may_set_rate` →
  `docs/history/audit-2026-08-19-architecture.md`
