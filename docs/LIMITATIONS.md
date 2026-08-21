# Known limitations

What this system deliberately does **not** do. Open work lives in `docs/todo/`,
one file per item; the test that separates the two is whether there is a fix and
a *done when*. If there is, it belongs there, not here.

## Accepted

- No email notifications, and only a single currency (`CURRENCY` in `.env`).
- **The no-double-booking constraint is PostgreSQL-only.** SQLite cannot express
  an exclusion constraint, so on SQLite the application-level check in
  `_assert_room_free` stands alone and a genuine write race is theoretically
  open — SQLite serialises writers, which mitigates it in practice. Treat
  PostgreSQL as the supported deployment target for anything real. This is one of
  the invariants indexed in `CLAUDE.md`.

## Decided against, with the trigger that would reopen it

Recorded so the next reader knows these were considered rather than missed. None
is a defect; each is a decision waiting for one specific thing to happen.

### Explicit inventory (`room_nights`) instead of derived overlap

Availability is derived on every read by scanning reservations for date overlap.
The PostgreSQL exclusion constraint makes that *correct* under concurrency, which
was the urgent part. A materialised `room_nights(room_id, night)` table would
additionally give O(1) availability lookups, work identically on SQLite, and
provide the natural home for per-night rates, allotments and deliberate
overbooking.

**Trigger:** the first of those features — `docs/todo/011-rate-plans.md` or
`docs/todo/013-deliberate-overbooking.md`. Seasonal rates force this model
anyway, so do it then rather than twice.

### `property_id` / multi-tenancy

There is no `property_id` anywhere; the schema describes exactly one hotel. That
is the right shape for what this is, and it is worth *deciding* about before the
schema calcifies, because adding it later touches every table and every query.

**Trigger:** any suggestion that a second property might exist.

### Transaction boundaries live in the services

Every service method calls `self.db.commit()`, so a router cannot compose two
service calls atomically. The walk-in flow already composes two — a guest is
registered and committed, then the reservation is created — which is where this
is felt first: a walk-in that loses the room to a conflict leaves the guest
registered with no booking. Tolerable, because the guest record is reused on the
next attempt.

**Trigger:** the first flow where a partial result is *not* tolerable — check out
*and* issue the invoice as a single unit, say, or a group check-in
(`docs/todo/014-group-bookings.md`). The conventional answer is a unit-of-work
dependency that commits once per request.
