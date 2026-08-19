# Open bugs

Functional defects that are not security issues — those live in
`SECURITY-TODO.md`.

**Nothing is open right now.**

The eighteen findings of the architecture and production-readiness audit of
**2026-08-19** were all fixed the same day; the details, the reproductions and the
measured figures are in the "Architecture & production-readiness audit of
2026-08-19" section of CLAUDE.md, each with its regression test. The two entries
this file carried before that (the overdue guest who disappeared from the front
desk, and the housekeeping menu clipped by its room card) were closed on the
same date and are recorded there too.

When something is found, describe it here the way those were: symptom, where in
the code, what was measured or reproduced, and what the fix should be — then move
it into CLAUDE.md with its regression test once it is closed.

---

## Deliberately not done

Recorded so the next reader knows these were considered rather than missed. None
of them is a defect; each is a decision with a trigger.

### Explicit inventory (`room_nights`) instead of derived overlap

Availability is derived on every read by scanning reservations for date overlap.
The PostgreSQL exclusion constraint added in the audit makes that *correct* under
concurrency, which was the urgent part. A materialised
`room_nights(room_id, night)` table would additionally give O(1) availability
lookups, work identically on SQLite, and provide the natural home for per-night
rates, allotments and deliberate overbooking.

**Trigger:** the first of those features. Seasonal rate plans force this model
anyway, so do it then rather than twice.

### `property_id` / multi-tenancy

There is no `property_id` anywhere; the schema describes exactly one hotel. That
is the right shape for what this is, and it is worth *deciding* about before the
schema calcifies, because adding it later touches every table and every query.

**Trigger:** any suggestion that a second property might exist.

### The frontend is unbundled and untested

Roughly 1,400 lines of Alpine components live inside `<script>` tags across ten
templates — unlinted, untyped, untested and invisible to `ruff` or any other
tool. Moving each to `static/js/pages/<page>.js` needs no build step.

**Trigger:** the CSP work in `SECURITY-TODO.md` §2.1. `unsafe-inline` cannot
leave `script-src` while the components live in the HTML, so that item depends on
this one.

### Transaction boundaries live in the services

Every service method calls `self.db.commit()`, so a router cannot compose two
service calls atomically. It works today because no flow needs two. The moment
one does — check out *and* issue the invoice as a single unit, say — there is no
seam to put it in, and the conventional answer is a unit-of-work dependency that
commits once per request.

**Trigger:** the first flow that needs two service calls to succeed or fail
together.

### Product gaps

Not defects, but the things a hotel would ask for next, roughly in order of
value:

- **Audit log.** The highest-value item missing from this system. Attribution
  exists where money moves (`created_by_id`, `recorded_by_id`, `waived_by_id`),
  but there is no before/after trail for ordinary edits — a price change or a
  date change is attributed to nobody. `actor, action, object, before, after, at`
  in one table; the service layer is already the single choke point to write it
  from. Also tracked in `SECURITY-TODO.md` §4.
- **Room move and stay extension as first-class operations.** Both are done today
  by `PATCH`-ing `room_id` or `check_out_date`, which silently re-prices at the
  new room type's base rate and leaves no record that a move happened. They are
  the two most common front-desk operations after check-in.
- **Rate plans.** `nightly_rate` is one number per booking, so seasonality means
  a manager overriding by hand every time — which is most of why the manager-only
  rate override exists at all.
- **Cancellation policy and deposits.** `cancel()` takes a reason and, for
  in-house stays, a waiver. It has no concept of a fee, a deadline or a forfeited
  deposit, so every cancellation is free.
- **Deliberate overbooking.** Impossible by construction, and real hotels oversell
  by a policy percentage because no-shows are predictable — `NO_SHOW` is already
  tracked, so the data to set the policy is being collected. Worth adding only
  *after* the exclusion constraint, so the rule has an explicit, auditable
  exception rather than a race condition standing in for one.
- **Group bookings.** One reservation is strictly one room.
