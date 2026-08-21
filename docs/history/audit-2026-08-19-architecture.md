<a id="architecture-audit-2026-08-19"></a>

# Architecture & production-readiness audit of 2026-08-19 (closed same day)

The third review, and the one that reached a different class of defect. The two
before it walked code paths and found real issues; this one asked what **states**
the application can be driven into. Every finding below was reproduced against
the running app before it was fixed, and each has a regression test.

**Critical — the reservation and billing core.**

- ~~Two guests could be checked into the same room~~ — `check_in()` validated
  status, arrival date and `MAINTENANCE`, and never asked whether anybody was
  still in the room. Overlap uses strict comparisons on purpose, so a stay
  ending today and one starting today are both legal on the calendar — correct
  for *selling* a room, wrong for *occupying* it. **This was the root cause of
  the room-502 incident recorded in
  `docs/history/review-2026-08-17.md`**; widening `arrivals_on()` /
  `departures_on()` to `<=` fixed the symptom, which was that the result was
  invisible, and left the state reachable. Reproduced on the demo data before
  the fix: room 502, two `checked_in` reservations, both on the in-house list.
  `check_in()` now refuses while `active_for_room()` returns anything, naming the
  occupant and their due-out date, and `active_for_room()` returns a **list**
  rather than `.first()` so the impossible state is detectable instead of
  silently truncated to whichever row the database happened to return first.
  Tests: `test_a_room_cannot_hold_two_checked_in_stays` and
  `test_check_in_succeeds_once_the_room_is_actually_empty`.
- ~~The no-double-booking rule existed only in Python~~ — `_assert_room_free()`
  reads and then the insert writes, with no lock and no constraint underneath,
  so two concurrent requests both read "free" and both committed. Textbook
  time-of-check/time-of-use, on the one invariant the module docstring names as
  its purpose. Confirmed that nothing below the service layer would stop it: two
  identical overlapping `CONFIRMED` stays committed with no `IntegrityError`.
  PostgreSQL now carries an `EXCLUDE USING gist` constraint on
  `room_id` plus `daterange(check_in_date, check_out_date, '[)')` where the
  status blocks. The half-open bound is exactly the strict-comparison semantics
  already implemented, so same-day turnover stays legal, and the partial `WHERE`
  means cancelling releases the nights. `_commit_booking()` translates the
  resulting `IntegrityError` into a 409, because an `IntegrityError` is not an
  `AppError` and would otherwise bypass the exception handlers as a 500. SQLite
  cannot express the constraint, so the race test lives in
  `tests/test_double_booking_pg.py`, skipped unless `DATABASE_URL` points at
  PostgreSQL, and CI runs it in a dedicated `postgres` job.
- ~~Invoice numbers came from `COUNT(*) + 1` and repeated~~ — a count is not a
  sequence: it goes backwards when a row is deleted, and
  `Invoice.reservation_id` cascades, so removing a reservation silently freed its
  number for reuse and handed one identity to two tax documents. Reproduced:
  `INV-2026-00002` issued, deleted, then issued again. Two concurrent issues also
  collided on the unique index as a 500. There is an `invoice_counters` table
  now, one row per year, incremented with `UPDATE … RETURNING` so the row lock
  serialises allocation; the migration seeds it from the highest number already
  issued per year. A gap — an allocation whose transaction rolled back — is
  expected and harmless: a sequence guarantees uniqueness and order, not the
  absence of gaps. `ReservationRepository.next_reference_seq()` had the same
  shape and was dead code, so it went rather than stay to be copied.

**High.**

- ~~Written-off money was still reported as owed~~ — the waiver *was* recorded
  (`waived_amount`, `waived_at`, `waived_by_id` all correct) and
  `ReportService._outstanding_balance()` never read it, so a debt a manager
  formally forgave kept appearing as receivable for ever — in the one number
  management reads to judge whether the ledger balances. Reproduced in the app:
  waived 1,982.40, outstanding 53,361.70 both before and after. It subtracts
  `COALESCE(waived_amount, 0)` now, and clamps **per reservation** rather than on
  the final sum, because `max(total, 0)` applied once at the end let an overpaid
  stay silently net off another stay's debt.
- ~~One report showed two different revenues, and ADR was meaningless~~ — the
  headline `total_revenue` was cash received in the window, VAT included, while
  `_room_type_performance()` beneath it was accrued `total_price`, VAT excluded.
  Both on one screen, neither labelled, and they could never agree.
  `average_daily_rate` then divided one basis by the other's unit, so a
  prepayment read as a rate rise: 354.00 for a room sold at 150.00, a 136%
  overstatement of the headline management metric. Revenue is **accrual**
  throughout now — the accommodation charge earned by the nights *consumed* in
  the window, net of tax, which is the basis occupancy and ADR were already on —
  and cash is reported separately as `cash_collected`, because a hotel needs
  both. The report screen names each. Verified on the demo data: room revenue
  33,945.00 equals the sum of the room-type table exactly, ADR 197.35 equals
  33,945 ÷ 172 nights, and cash 38,415.00 equals the payment-method split. Same
  class of defect as the two unit mismatches already fixed in
  `docs/history/review-2026-08-17.md` — a number
  printed without its unit.
- ~~bcrypt and PDF rendering ran on the event loop~~ — every handler is
  `async def`, but `pwd_context.verify()` and ReportLab's `doc.build()` are
  synchronous CPU-bound calls, so while either ran the process served nothing at
  all, `/health` included. Measured: one bcrypt verify 198 ms at cost factor 12;
  five concurrent logins a single **997 ms** stall in which an asyncio heartbeat
  never ran once; a ceiling of ~5 logins per second per worker on any hardware —
  so a shift signing in at 08:00 was a two-second freeze for everyone. Both go
  through `starlette.concurrency.run_in_threadpool` now; bcrypt releases the GIL,
  so a thread genuinely parallelises it. `hash_password_async`,
  `verify_password_async` and `waste_password_time_async` are what `AuthService`
  calls; the sync versions stay for non-request callers such as `seed.py`.
- ~~The migrations had drifted from the models~~ — `alembic check` failed. Three
  `ON DELETE SET NULL` clauses existed in the models and in no migration
  (`payments.recorded_by_id`, `payments.refunded_payment_id`,
  `reservations.waived_by_id`), so development, which builds its schema with
  `create_all()`, and production, which migrates, had structurally different
  foreign keys — on exactly the columns that record who took the money. Fixed on
  **both** engines: on SQLite through
  `batch_alter_table(copy_from=…, recreate="always")`, because fixing one engine
  and not the other is how the divergence arose in the first place. That snapshot
  has to carry the table's indexes and constraints too, since a batch rebuild
  produces exactly what it is given. `alembic check` runs in CI now, with a
  downgrade/upgrade round trip beside it.
- ~~The same state change was guarded by two different roles~~ —
  `PATCH /rooms/{id}` required a manager while `POST /rooms/{id}/status` was open
  to any staff member, and both reached `MAINTENANCE`, which removes a room from
  sale. Reproduced: 403 through one door and 200 through the other, same session.
  The role belongs to the change rather than to the route, so it lives in
  `RoomService._assert_may_take_out_of_service` — the same reasoning as
  `_assert_may_set_rate` in the security rules in `CLAUDE.md`.
  Housekeeping keeps `CLEANING` and `AVAILABLE`.
- ~~`TRUSTED_HOSTS` defaulted to `*` and was exempt from the boot check~~ — the
  security rules in `CLAUDE.md` say a security-relevant setting gets a check in
  `_refuse_unsafe_production`; this one was added without it, so production
  started with the Host header check disabled, and the shipped `docker-compose`
  did exactly that. The check exists now, and compose sets real hostnames,
  demands a `POSTGRES_PASSWORD` instead of shipping `hotel`/`hotel`, stops
  publishing 5432 to the host, and runs uvicorn with `--proxy-headers` so the
  rate limiter sees real client addresses.

**Medium.**

- ~~A room with confirmed bookings could go out of service silently~~ — the guard
  looked only at checked-in guests, so a room with a stay five days out returned
  200 and that booking stayed alive and unfulfillable until the guest arrived and
  check-in refused it. `blocking_for_room()` names the affected bookings in the
  error now, so somebody rehouses them at the time.
- ~~Room-type capacity could shrink below an existing booking~~ — reducing a
  Double from 2 to 1 while a two-guest stay was in it returned 200, leaving that
  booking in violation of a rule it could no longer be edited without tripping.
  `largest_party_for_type()` and `largest_party_for_room()` refuse it, on the
  capacity change and on the sideways route through `room_type_id`.
- ~~Payments had no idempotency~~ — the identical body posted twice created two
  rows, so a double-click or a client retry booked the guest's money twice.
  `reference` is unique per reservation now, checked in the service for a
  readable message and enforced by `uq_payment_reservation_reference` for the
  concurrent case. A refund counter-entry takes `REFUND-<reference>` so it does
  not collide with the row it reverses. Payments with no reference are still free
  to repeat — two identical cash amounts are a normal thing to record.
- ~~Measured N+1s, and the hottest column had no index~~ —
  `GET /reports/occupancy-trend?days=90` issued **92** statements, and the report
  close to 370 at its 366-day cap, because `occupied_on()` was called once per
  day. `occupied_per_day()` does it in one query, expanding nights in Python for
  the same reason `revenue_by_day` does: no dialect-specific date truncation.
  `payments.paid_at` carried no index although every revenue query range-filters
  on it, and the overlap check had only single-column indexes; both are covered
  now (`ix_payments_paid_at`, `ix_reservation_room_stay`). `RoomService.board()`
  was the worst offender at 1 + 2N and turned out to be dead code — deleted.
- ~~Pricing arithmetic was duplicated in three places outside `pricing.py`~~ —
  `rate × nights` was recomputed in `ReservationService._price()`,
  `PaymentService.folio()` and `RoomService.find_available()`. The folio case was
  the dangerous one: it derived `subtotal` itself while taking `total` from
  `total_due()`, then computed `tax_amount = total − subtotal`, so two
  independent sources described one bill and the tax line quietly absorbed any
  difference between them. `pricing.accommodation_charge()` is the single
  definition now, with `tax_on()` beside it, and the folio derives every figure
  from the stored charge.
- ~~Nothing enforced the project's own rules~~ — 102 tests passed only when
  somebody remembered to run them. There is a CI workflow now
  (`.github/workflows/ci.yml`): `ruff check`, `pytest`, `alembic check` plus the
  downgrade round trip, an external assertion that production refuses to boot
  unsafely, a PostgreSQL job for the double-booking constraint, and advisory
  `pip-audit`. `pyproject.toml` carries the ruff configuration. This is the item
  that holds the rest in place: `alembic check` would have caught the drift the
  day it appeared, and `pip-audit` the `python-jose` CVEs before an audit did.
- ~~Guest data had no erasure path~~ — `delete()` refuses anybody who has ever
  had a reservation, which is right, because the relationship cascades to
  payments and invoices; it also meant erasure was impossible for exactly the
  guests whose data was worth erasing. `GuestService.anonymise()` clears the
  contact fields, replaces the name with a tombstone and the document number with
  a per-id placeholder (the column is NOT NULL and unique on the pair), and
  leaves the reservations, payments and invoices pointing at the same row — so
  occupancy, revenue and the VAT record are untouched. Manager-only,
  irreversible, and refused while the guest is still in the hotel.
- ~~`FailedLoginTracker` grew without bound~~ — two plain dicts keyed on the
  *submitted* email address that only ever shed an entry on a successful login,
  so every address an attacker tried stayed for the life of the process. The rate
  limit caps the rate, not the total. Entries expire and the store is capped now,
  evicting least-recently-touched, and an account under active attack keeps its
  lock. Redis is still the real fix for *sharing* the counters between instances
  and remains tracked in `docs/todo/`.

**Low, and the patterns behind them.**

- ~~`/health` could not fail~~ — it returned a literal, so an orchestrator would
  keep routing traffic to a container whose database was unreachable. It runs
  `SELECT 1` and answers 503 on failure, still saying nothing about environment,
  version or the error.
- ~~The last-admin guard loaded every user into Python and raced~~ — two
  concurrent demotions could each see the other as "the other admin".
  `count_active_admins()` counts in SQL with `with_for_update()`, falling back
  cleanly on SQLite, which has no row locking and a single writer anyway.
- ~~State travelled in query strings~~ — `?note=` on refund and
  `?allow_outstanding_balance=` on check-out put a manager's free-text
  justification and a financial decision into every access log and proxy history
  along the way. Both are request bodies now (`RefundRequest`,
  `ReservationCheckOut`), as is the room status (`RoomStatusUpdate`).
- ~~`CHECK_IN_HOUR` and `CHECK_OUT_HOUR` were configured and read by nothing~~ —
  the hotel's stated turnover window existed only in the `.env` file. The front
  desk shows it now. Deliberately still not enforced: early check-in and late
  check-out are decisions taken at that desk, and the rule that actually matters
  is the occupancy guard above.
- ~~Dead code offering a wrong version of a rule stated correctly elsewhere~~ —
  `BaseRepository.update()` filtered `None` against a `_nullable_fields`
  attribute no model defined, a permanently dead branch reimplementing the
  services' `NULLABLE_UPDATE_FIELDS` badly. Deleted, along with
  `BaseRepository.list()` and `count()`, `PageParams`,
  `RoomService.occupancy_snapshot()` and `RoomService.board()` — nothing called
  any of them.

**The lesson worth keeping.** Two prior reviews read this code carefully and
found real bugs, and none of the above. The difference is the question: "is this
function correct?" versus "what states can the application be driven into?" The
check-in defect was found by asking what the calendar permits that the building
does not; the waiver defect by asking whether the number that says money was
written off actually changes. Ask a booking system the second question
regularly — and note that the absence of CI is what let the schema drift and the
state gaps sit undisturbed, which is why the workflow ranked ahead of every
defect it would have caught.
