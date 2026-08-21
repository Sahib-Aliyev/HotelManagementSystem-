---
paths:
  - "app/services/reservation_service.py"
  - "app/services/room_service.py"
  - "app/repositories/reservation_repo.py"
  - "app/repositories/room_repo.py"
  - "app/routers/api/reservations.py"
  - "app/routers/api/rooms.py"
---

# Reservations and rooms

The calendar decides what can be sold; housekeeping status answers a different
question. Most of the defects in this area came from mixing the two.

## Standing rules

- **Selling a room and occupying it are different questions.** Overlap is
  checked with strict comparisons, so same-day turnover is sellable — a stay
  ending today does not collide with one starting today. That is right for the
  calendar and not enough for the building: `check_in()` also refuses while
  `active_for_room()` returns anything, because a room cannot hold two guests at
  once whatever the dates allow. `active_for_room()` returns a **list** on
  purpose; `.first()` hid the contradiction by reporting one of the two rows.
- **A room's housekeeping status may not contradict the calendar.** A room with
  a guest checked into it is `OCCUPIED`, whatever housekeeping does to it.
  Cleaning an occupied room is normal (it happens daily), so `CLEANING` is
  allowed — but marking it clean resolves to `OCCUPIED`, not `AVAILABLE`
  (`RoomService.update_room`). `MAINTENANCE` on an occupied room is refused
  outright. The two statuses answer different questions and only the calendar
  decides what can be sold: `find_available()` filters on overlap and
  `MAINTENANCE`, never on `OCCUPIED`/`CLEANING`, so a room can be sold for
  future dates while someone is still in it.

## Lifted from the audits

- `blocking_for_room()` names the affected bookings when a room is taken out
  of service, so somebody rehouses them at the time instead of discovering it
  at check-in → `docs/history/audit-2026-08-19-architecture.md`
- `largest_party_for_type()` and `largest_party_for_room()` refuse a capacity
  shrink below an existing booking, including the sideways route through
  `room_type_id` → `docs/history/audit-2026-08-19-architecture.md`
- `arrivals_on()` and `departures_on()` filter with `<=` and are ordered
  most-overdue-first, and `upcoming_for_room()` carries no date filter: an
  overdue stay must not fall out of every view while it still holds its room →
  `docs/history/review-2026-08-17.md`
