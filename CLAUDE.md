# HotelManagementSystem

Hotel guest registration and reservation management system. FastAPI backend,
server-rendered Jinja2 + Alpine.js + TailwindCSS frontend. A learning /
portfolio project — there are no real hotel users; it runs on PostgreSQL or
SQLite.

## Commands

- Server (dev): `.venv\Scripts\python.exe run.py` → http://127.0.0.1:8000, API docs `/api/docs`
- Tests: `.venv\Scripts\python.exe -m pytest -v`
- Lint / format: `.venv\Scripts\python.exe -m ruff check .` and `ruff format .`
- Schema drift check: `.venv\Scripts\alembic.exe check` — must pass; CI runs it
- A single test file: `.venv\Scripts\python.exe -m pytest tests/test_reservations.py -v`
- The double-booking race test needs PostgreSQL and is skipped on SQLite,
  which cannot express the constraint:
  `DATABASE_URL=postgresql+asyncpg://... .venv\Scripts\python.exe -m pytest tests/test_double_booking_pg.py`
- Demo data: `.venv\Scripts\python.exe seed.py` (`--reset` rebuilds from scratch)
- New migration: `.venv\Scripts\alembic.exe revision --autogenerate -m "..."`
- Apply migrations: `.venv\Scripts\alembic.exe upgrade head`
- Full stack (with Postgres): first `export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")`, then `docker compose up` — compose runs with `APP_ENV=production`, so it deliberately refuses to start without a key

## Architecture rule

The layer order is fixed: `routers/api` → `services` → `repositories` → SQLAlchemy model.

- A router never writes an ORM query directly — it calls the matching
  `services/*Service` method and checks the role (`StaffUser` / `ManagerUser` /
  `AdminUser`).
- Every SQL query lives in `repositories/` — nowhere else.
- Business rules (overbooking, pricing, VAT, lifecycle transitions) live only in
  `services/`, never duplicated in a router or a template.
- **Two invariants live in the database as well, and that is deliberate.** The
  no-double-booking rule is a PostgreSQL exclusion constraint
  (`no_double_booking`) and a receipt number is unique per reservation
  (`uq_payment_reservation_reference`). A service check alone cannot close a
  read-then-write race, so both exist twice: the Python check produces the
  message a receptionist can act on, and the constraint is what actually holds
  under concurrency. Anything that writes a booking must therefore go through
  `ReservationService._commit_booking()`, which turns the resulting
  `IntegrityError` into a 409 — an `IntegrityError` is not an `AppError`, so
  unmapped it bypasses the exception handlers and answers 500.
- When adding an endpoint, remember to register the router in
  `app/routers/api/__init__.py`. Sub-routers such as invoices and staff are not
  separate files but extra `APIRouter` objects inside existing ones — e.g.
  `payments.invoices_router`, `auth.staff_router`.

## Conventions

- Do not add a docstring or comment to a new function just to describe what it
  does. One line is enough, and only when the WHY is not obvious.
- Every new business rule needs a matching test in `tests/` — especially
  anything touching overlap/overbooking, pricing, or role permissions.
- Frontend API calls always go through the `api()` helper in
  `app/static/js/app.js`; never call `fetch()` directly. The 401 handling and
  the error format are implemented only there.
- When adding a field to a form, check that it exists in the backend schema
  (`app/schemas/`) and in *every* creation path (e.g. both `ReservationCreate`
  and `QuickBookingCreate`). `nightly_rate` was lost exactly this way — see
  "Fixed bugs".
- Hiding a button in the UI is not a role check. Every endpoint must enforce it
  server-side too, via the dependencies in `app/core/deps.py`.
- **All money arithmetic lives in `app/services/pricing.py`.**
  `accommodation_charge(rate, nights)`, `tax_on(subtotal)` and
  `total_due(reservation)` are the only definitions; nothing recomputes
  `rate × nights` or a tax share of its own. Three places used to, and the folio
  was deriving its subtotal one way while taking its total another, so the tax
  line silently absorbed the difference between them.
- **Never compare a payment against `Reservation.total_price` directly** —
  it is net of tax. What the guest actually owes is
  `app/services/pricing.py::total_due()`, which adds VAT. Using
  `total_price` alone lets a guest check out having paid the room charge but
  never the tax — see "Fixed bugs". The dashboard aggregate in
  `ReportService._outstanding_balance` is the same rule in SQL form.
- **Payments are append-only.** A refund is a new `Payment` row with
  `refunded_payment_id` pointing at the settled row it reverses; the settled
  row is never edited. Anything that sums money therefore has to go through
  `is_cash_movement()` and `signed_amount()` in
  `app/repositories/payment_repo.py`, which count a counter-entry as negative.
  Filtering on `status == PAID` alone silently ignores every refund.
- **Money the hotel gives up is written down.** Both paths that forgive a
  balance — check-out with `allow_outstanding_balance`, and cancelling a stay
  that is already checked in — require a manager and record
  `waived_amount` / `waived_at` / `waived_by_id` on the reservation
  (`ReservationService._record_waiver`). A new way to forgive money must do
  the same.
- **Selling a room and occupying it are different questions.** Overlap is
  checked with strict comparisons, so same-day turnover is sellable — a stay
  ending today does not collide with one starting today. That is right for the
  calendar and not enough for the building: `check_in()` also refuses while
  `active_for_room()` returns anything, because a room cannot hold two guests at
  once whatever the dates allow. `active_for_room()` returns a **list** on
  purpose; `.first()` hid the contradiction by reporting one of the two rows.
- **A report figure has to name its basis.** `total_revenue` is accrual (nights
  consumed in the window, net of tax) and `cash_collected` is cash (payments
  received, VAT included). They are different numbers and both are correct.
  Never divide one by the other, and never put an unlabelled "revenue" on a
  screen beside a breakdown computed the other way — see "Fixed bugs" twice over.
- **A room's housekeeping status may not contradict the calendar.** A room with
  a guest checked into it is `OCCUPIED`, whatever housekeeping does to it.
  Cleaning an occupied room is normal (it happens daily), so `CLEANING` is
  allowed — but marking it clean resolves to `OCCUPIED`, not `AVAILABLE`
  (`RoomService.update_room`). `MAINTENANCE` on an occupied room is refused
  outright. The two statuses answer different questions and only the calendar
  decides what can be sold: `find_available()` filters on overlap and
  `MAINTENANCE`, never on `OCCUPIED`/`CLEANING`, so a room can be sold for
  future dates while someone is still in it.
- **A schema field typed `X | None` is optional on input, not nullable.** An
  explicit JSON `null` survives `model_dump(exclude_unset=True)`, so the
  services drop `None` values before merging them (`NULLABLE_UPDATE_FIELDS` in
  `reservation_service.py` and `guest_service.py` list the fields that really
  can be cleared). Without that, `null` reaches the arithmetic or a NOT NULL
  column and becomes a 500.

## Frontend design system

The templates share one vocabulary of component classes instead of repeating
long utility strings. Reuse it rather than hand-rolling a new card or button.

- The classes live in the `<style type="text/tailwindcss">` block in
  `base.html`, inside `@layer components`, so the Tailwind CDN compiles them
  into its own sheet and a utility written on the element still wins over the
  component default. `.card`, `.card-hd`, `.card-bd`, `.card-ft`, `.card-lift`,
  `.btn` (+ `.btn-primary` / `.btn-accent` / `.btn-outline` / `.btn-ghost` /
  `.btn-danger` / `.btn-solid-danger`, sized with `.btn-sm` / `.btn-xs`),
  `.btn-icon`, `.input` (+ `.input-sm` / `.input-error`), `.field`, `.hint`,
  `.error-text`, `.badge`, `.chip` (+ `.chip-on`), `.tbl`, `.nav-link`
  (+ `.nav-link-on`), `.panel-title`, `.panel-sub`, `.eyebrow`, `.tile-icon`,
  `.stat-value`.
- `app/static/css/app.css` holds only what utilities cannot express: design
  tokens, tabular figures, the skeleton sheen, the `.stagger` cascade, the
  active-nav indicator, `.edge-top`, the focus ring, the skip link and print
  rules. **`@apply` does not work there** — that file is served as a static
  asset and Tailwind never sees it.
- `brand` is a single coherent indigo ramp and `accent` a full emerald ramp.
  Do not introduce a one-off hex; if a new tint is needed, add the step to the
  ramp in `base.html`.
- Status colours come from `badgeClass(status)` and `dotClass(status)` in
  `app.js`, which map a status to one of the shared tones. Add new statuses to
  `STATUS_TONES`, never to a template.
- Chart styling is centralised in `chartTheme()`, which also sets the Chart.js
  defaults (font, tooltip). Read colours from it instead of hard-coding them.
- `/static` is cache-busted with `?v={{ asset_version }}`, derived from the
  mtimes of `app.css` and `app.js` in `app/routers/web.py`. Any new static
  asset referenced from a template should carry the same query.
- **A popover inside a grid card has to leave the card.** The cards in
  `rooms.html` are ~155px wide at the two-column breakpoint and the menu is
  `w-44` (176px), so anchored inside the card it overflows the grid in every
  direction and is clipped by whichever ancestor scrolls. `cardMenu()` in
  `app.js` is the pattern: `<template x-teleport="body">` keeps the card's
  Alpine scope but moves the element out, and the menu is positioned with
  fixed coordinates measured off its button and clamped to the viewport. It
  follows the button while the page scrolls and closes once the button leaves
  the screen. Popovers anchored in the top bar need none of this — there the
  viewport edge is the only boundary.
- **Never drive a popover's position with `:style` while `x-show` controls it.**
  A style binding rewrites the whole inline `style` attribute, which wipes the
  `display: none` that `x-show` wrote — every menu on the page then stays
  rendered, invisible but real, parked at whatever coordinates it last had.
  Write positions imperatively (`el.style.left = …`), and leave `display` to
  `x-show`.
- **Listeners bound to a teleported element do not fire**, `.window`
  modifiers included. Put the close handlers (`@click.outside`,
  `@keydown.escape.window`, `@scroll.window`, `@resize.window`) on the wrapper
  that stays in the tree, which shares the same Alpine scope.
- **`x-transition` hands `display` to a completion callback.** In a background
  tab that callback never runs, so a transitioned `x-show` element can stay
  rendered. Fine for a drawer the user is looking at; not fine for a menu whose
  hidden state has to be reliable, which is why the room-card menu has no
  transition.
- **"Sleeps up to N" is a room, "N guest(s)" is a booking.** Capacity belongs to
  the room type, is shared by every room of that type and does not follow the
  booking — a Family Room sleeps up to 4 whether one guest or four are in it. It
  is also the ceiling a booking is validated against, so it cannot follow one.
  The party size belongs to the stay. Both numbers belong on a room card and
  they are stated together rather than in separate places where they read as
  rival answers to the same question: an occupied room says **"1 of 4 guests"**,
  an empty one **"Sleeps up to 4"**, and a "Next arrival" block names the party
  that is coming (`27 Aug · 1 guest`). Printing one
  in the other's words puts two different numbers for the same room on two
  screens — see "Fixed bugs". `settings.html` and `new_reservation.html` already
  used "Sleeps"/"sleeps"; keep to it.
- **Anything counted in two units has to name the unit.** "In house" is five
  stays and nine people at the same time; "occupied" is five rooms. A bare
  number next to another bare number reads as a contradiction even when both are
  right, so the dashboard tile says *Guests in house* with `N stay(s)` under it,
  and the front-desk column says `N stay(s) · N guest(s)`. Same for arrivals and
  departures: those count stays, not people.
- **The sidebar is `lg:sticky lg:top-0 lg:h-screen`, not `lg:static`.** As a
  static flex child it stretched to the height of the page, so scrolling a long
  list carried the whole navigation off screen and left an empty column behind.
  It keeps `left: auto` from `lg` up — a sticky flex child has no reason to
  offset horizontally — and animates only `width` and `transform`, because
  `transition-all` on a full-height sticky layer animates far more than the
  collapse and is a repaint hazard.
- **A `<template x-if>` inside an `<svg>` silently breaks Alpine** — SVG is
  foreign content, so the element has no `.content` and Alpine throws on
  `cloneNode`. Bind the shape instead (`<path :d="…">`), as the toast host does.

## Security rules

These came out of the security audit. Breaking one breaks a test in
`tests/test_security.py`.

- **Money and pricing fields are authorised in the service layer, not in the
  router.** `nightly_rate` arrives through three separate endpoints (`create`,
  `walk-in`, `PATCH`), so the permission check lives in
  `ReservationService._assert_may_set_rate`, which all three pass through.
  Follow the same pattern for any new manager-only field.
- **Never type a schema field as `dict`.** Use a concrete Pydantic model.
  `QuickBookingCreate.guest` was a `dict`, which skipped guest validation
  entirely and turned bad input into a 500 instead of a 422.
- **Tokens carry a `pwf` claim** — a fingerprint of the user's password hash
  (`app/core/security.py`). It is verified on every request, so changing a
  password immediately kills every session issued under the old one. Do not
  drop it when adding new claims.
- **Rate-limit every new authentication endpoint** (`@limiter.limit(...)` from
  `app/core/ratelimit.py`). The decorator only works if the function has a
  `request: Request` parameter — without it the limit silently does nothing.
- **When adding a security-relevant setting**, add a check to
  `config.py::_refuse_unsafe_production` as well: production must not boot on
  development defaults.
- **Administrator count**: deactivating or demoting the last active admin is
  blocked in `AuthService`. Both `deactivate()` and `update_user()` can reach
  that state, so the guard exists in both.
- **Tokens also carry a `tv` claim** — the user's `token_version`, bumped by
  `AuthService.revoke_sessions()` on logout and verified in `deps.py`. Without
  it, "sign out" only deleted the cookie while the JWT stayed valid for its
  full lifetime (and `Authorization: Bearer` accepts it). Keep both `pwf` and
  `tv` when adding claims.
- **Rules that `create` enforces have to hold on `PATCH` too.** The stay range
  lives in one place, `schemas/reservation.py::stay_range_error`, used by
  `ReservationCreate`, `QuickBookingCreate` and `ReservationService.update`.
  PATCH re-derives the dates and re-prices from them, so an unguarded PATCH
  reaches every rule create protects.
- **A GET must not write.** The session cookie is `samesite="lax"`, so a
  top-level GET navigation from anywhere carries it — a mailed link is enough.
  `render_pdf()` therefore reads an issued invoice and 404s otherwise; issuing
  is the explicit POST.
- **Every `ge`/ceiling check must be status-independent** where the status
  comes from the client. `PaymentCreate.status` is client-settable, so gating
  the overpayment ceiling on `status == PAID` let any amount through as
  `pending`.

## Known limitations

Open work lives in two separate files: **`SECURITY-TODO.md`** (security findings
and the pre-deployment checklist) and **`BUGS-TODO.md`** (functional defects that
are not security issues). What follows is limitations that are deliberately
accepted.

- No email notifications, and only a single currency (`CURRENCY` in `.env`).
- The CSP still allows `unsafe-inline` and `unsafe-eval`, because Tailwind,
  Alpine and Chart.js load from CDNs and Tailwind compiles styles in the
  browser. Vendoring those three files is what allows a strict CSP.
- Rate limiting is per-IP with a per-account lockout on top
  (`ACCOUNT_LOCK_AFTER_FAILURES`), and defaults to in-memory storage: behind a
  proxy the real client IP must be forwarded, and more than one instance needs
  `RATE_LIMIT_STORAGE_URI` pointed at Redis. The per-account counter is
  in-process too, with the same caveat — it is bounded and expiring now, so it
  cannot grow without limit, but two instances still keep separate counts.
- **The no-double-booking constraint is PostgreSQL-only.** SQLite cannot express
  an exclusion constraint, so on SQLite the application-level check in
  `_assert_room_free` stands alone and a genuine write race is theoretically
  open — SQLite serialises writers, which mitigates it in practice. Treat
  PostgreSQL as the supported deployment target for anything real.
- No audit log, and it is the highest-value thing missing. Who took a payment
  (`recorded_by_id`), who refunded it (the
  counter-entry's `recorded_by_id`), who created a reservation
  (`created_by_id`) and who waived a balance (`waived_by_id`) are recorded, but
  there is no before/after trail for ordinary edits — a price change or a date
  change is not attributed to anyone.
- No two-factor authentication.

## Language rule

**Everything written down in this repository is in English** — without
exception. That covers every `*.md` file (this one, `README.md`,
`SECURITY-TODO.md`, `BUGS-TODO.md`), every commit message, and every comment
and docstring in the code. Commits before `2026-08-19` are in Azerbaijani;
that is history, not a precedent — do not add more.

## Git / commit rule

- Write a **broad and detailed description** on every commit before pushing:
  what changed, why it changed, which files it touched. A single line like
  "fix bug" is not enough.
- Format: a short summary on the first line, a blank line, then bullets with
  the reasoning and details.
- **The history is documentation.** When picking this project up — reading
  CLAUDE.md and the two TODO files to understand where it stands — read the
  commit log as well (`git log`, and `git log -p <file>` for anything
  surprising). The `*.md` files say what is true now; the commits say how it
  got there and what was rejected on the way. Anyone, Sahib or Claude, should
  be able to understand a change from its message alone, without re-reading the
  diff.
- Push to `origin` (GitHub) once the tests pass, so the remote history is the
  same documentation the local one is.

## Fixed bugs (for the record)

- ~~The manager rate override did not work on walk-in reservations~~ —
  `nightly_rate` was added to `QuickBookingCreate` and moved into the `common`
  object in `new_reservation.html`. Regression test:
  `tests/test_reservations.py::test_walk_in_honours_a_nightly_rate_override`.
- ~~The rooms page could lose current guests once there were more than 100
  reservations~~ — an `order=asc` option was added to the reservation search;
  `rooms.html` now sends separate, naturally bounded queries for "occupied"
  (bounded by room count) and "upcoming" (bounded by `date_from` plus ascending
  order).
- ~~The `next` parameter on login was an open-redirect risk~~ — only relative
  paths starting with `/` (and not `//`) are accepted now.
- ~~Toast notifications never drew an icon~~ — the icon was chosen with three
  `<template x-if>` elements nested inside the `<svg>`. SVG is foreign content
  to the HTML parser, so those templates have no `.content` and Alpine threw
  `Cannot read properties of undefined (reading 'cloneNode')` on every page
  load. The host now binds `<path :d="iconPath(t.type)">`.
- ~~The settings page advertised an 8-character password policy~~ — the real
  rule in `app/schemas/auth.py` is 10 characters plus upper case, lower case
  and a digit, so a valid-looking password was rejected by the server. The page
  now shows a live checklist mirroring `_strong_enough()`.
- ~~Editing the CSS or JS did not reach the browser~~ — `/static` is served
  with a long cache and the templates linked the files without a version, so a
  stale `app.css` could persist. Both now carry `?v={{ asset_version }}`.

### Security audit (2026-08)

- ~~The login endpoint was wide open to brute force~~ — `slowapi` was
  installed and `app.state.limiter` was set, but `default_limits` was empty and
  no endpoint carried `@limiter.limit`, so the control was entirely dead. Now
  `/auth/login` is 10/min and `/auth/change-password` is 5/min
  (`app/core/ratelimit.py`).
- ~~A receptionist could book at any price by sending `nightly_rate`~~ — none
  of the three endpoints checked permission, and the `PATCH` path had not been
  documented at all. `ReservationService._assert_may_set_rate` now covers all
  three.
- ~~`PATCH /staff/{id}` could deactivate or demote the last administrator~~ —
  `deactivate()` had a guard, but PATCH reached the same state sideways through
  the `role` and `is_active` fields and could leave the system with no admin.
- ~~Changing a password did not invalidate existing sessions~~ — a stolen token
  kept working for 12 hours. Tokens now carry a fingerprint of the password
  hash (`pwf`), verified on every request; the session of the user who changed
  the password is re-keyed automatically.
- ~~Logging in with an unknown email skipped bcrypt entirely~~ — response time
  revealed which addresses were registered, even though the message was
  deliberately identical. Both paths now pay for one bcrypt round
  (`waste_password_time`).
- ~~Production started on development defaults~~ — the placeholder `SECRET_KEY`
  could sign sessions. `config.py::_refuse_unsafe_production` now refuses at
  boot (shipped or short key, `DEBUG=true`, `CORS_ORIGINS=*`).
- ~~`/api/docs` and the OpenAPI schema were public in production~~ — they are
  enabled only in development now.
- ~~`QuickBookingCreate.guest` was an untyped `dict`~~ — guest validation was
  skipped completely and bad input returned a 500; it is `GuestCreate` now.
- ~~Responses carried no CSP, HSTS or `Cache-Control`~~ — guest PII (passport
  number, phone, address) could linger in the browser cache. All non-static
  responses are `no-store` now.
- ~~`/health` leaked `APP_ENV`~~ — it returns only `{"status": "ok"}`.
- ~~The password policy was 8 characters with no class requirement~~ — now 10
  characters plus upper case, lower case and a digit, and the new password must
  differ from the current one.
- ~~`python-jose 3.3.0`~~ — CVE-2024-33663 and CVE-2024-33664; upgraded to
  3.4.0.

### Review of 2026-08-17 (closed 2026-08-19)

Every item section 2 of `SECURITY-TODO.md` listed, plus both functional bugs
from `BUGS-TODO.md`. Regression tests: `tests/test_reservations.py`,
`tests/test_payments.py`, `tests/test_security.py`.

- ~~`PATCH /reservations/{id}` skipped every date rule `create` enforces~~ —
  `ReservationUpdate` had no range validator and `update()` checked only
  `check_out > check_in`, so `{"check_out_date": "9999-12-31"}` returned 200
  with `nights: 2912213`. That took the room off sale until the year 9999 (every
  later booking failed `_assert_room_free` with no explanation in the UI) and
  re-priced the stay at 291,221,300.00 — past `Numeric(10, 2)`, which SQLite
  stores silently and PostgreSQL rejects mid-transaction as a 500. Backdating
  worked the same way and fed fabricated nights into occupancy and ADR. The
  rule now lives once in `stay_range_error()`, `update()` re-asserts
  "check-in not in the past" when the arrival date changes, and `_price()`
  refuses a total above the column's ceiling.
- ~~The dashboard's `outstanding_balance` was computed net of VAT~~ — the
  fourth call site of the bug fixed in `d0f8edc`, and the one number management
  reads to decide whether the ledger balances. It disagreed with the folio of
  every reservation by exactly the tax share.
- ~~The login open redirect was still reachable with a backslash~~ — the fix
  recorded above only rejected a literal `//` prefix. Per the WHATWG URL spec a
  backslash in the authority position of an http(s) URL is treated as a slash,
  so `?next=/\evil.example` resolved to `http://evil.example/` in Chrome,
  Firefox and Safari — a phishing page reached through a genuine, successful
  login. `login.html` now resolves the value against `location.origin` and
  compares origins instead of prefix-matching.
- ~~A receptionist could cancel a checked-in stay and erase the debt~~ —
  `cancel()` treated `CHECKED_IN` as an ordinary case. Cancelling removed the
  nights from occupancy and ADR, removed the money owed from the dashboard, and
  made `PaymentService.record` refuse payment afterwards, so the debt could not
  be collected even once someone noticed. It now needs a manager, and refuses
  outright while a balance is owed unless the manager passes `waive_balance`,
  which is recorded.
- ~~A refund overwrote the payment it reversed~~ — `refund()` set
  `status = REFUNDED` and replaced `note`, so the amount, the original note and
  any trace that a refund had happened were gone; a manager could take cash and
  leave the guest showing as unpaid. Refunds are counter-entries now
  (`refunded_payment_id`), the settled row is untouched, refunding twice is a
  409, and every money sum reads `is_cash_movement()` / `signed_amount()`.
- ~~`DELETE /guests/{id}` always returned 500, and the obvious fix was a trap~~
  — `Guest.reservations` is lazy-loaded, so touching it raised
  `MissingGreenlet`, which is not an `AppError` and bypassed the exception
  handlers. Fixing only the crash would have been worse: the guard blocked only
  *active* reservations while the relationship cascades to payments and
  invoices, so a manager could have wiped a guest's whole financial history in
  one request. Reservations are counted through the repository now and any
  reservation at all blocks the delete.
- ~~An explicit JSON `null` in `PATCH /reservations/{id}` was a 500~~ — see the
  `X | None` convention above.
- ~~`GET /invoices/reservation/{id}/pdf` wrote to the database~~ — it called
  `issue()`, so a GET created the invoice row and consumed a number from the
  sequence, froze a stale subtotal, and could be triggered by a link mailed to
  a staff member (the cookie is `samesite=lax`). The route is read-only now;
  the UI issues through `openInvoicePdf()` in `app.js`, which POSTs first.
- ~~Non-`PAID` payments bypassed the overpayment cap~~ — `99999999.99` as
  `pending` was accepted with no relation to what was owed.
- ~~`allow_outstanding_balance` was a receptionist-level, unrecorded waiver~~ —
  the VAT fix made the balance correct; this query parameter made paying it
  optional for the lowest role. Manager-only and recorded now, and the folio
  drawer says so instead of sending a request that will 403.
- ~~Logout did not revoke the token~~ — see the `tv` claim above.
- ~~An overdue guest disappeared from the front desk~~ — `departures_on()` and
  `arrivals_on()` matched the date exactly, so a stay whose check-out date had
  passed matched no day and appeared in no column, and a booking that never
  arrived fell out of every view while its room stayed blocked. That is how
  room 502 ended up with two simultaneous `checked_in` reservations. Both are
  `<=` now and ordered most-overdue-first; `upcoming_for_room()` dropped its
  `check_in_date >= today` filter so the rooms board stops describing a blocked
  room as free; and the dashboard, front desk, rooms and reservations screens
  all label how many days overdue something is
  (`fmt.overdueLabel`). Overdue arrivals get a manager-only "No show" button so
  they can be resolved rather than left holding inventory.
- ~~The housekeeping menu on a room card was clipped and unclickable~~ — three
  passes, because each one uncovered the next problem. (1) The card carried
  `overflow-hidden` to clip the status stripe to its rounded corners and the
  `⋮` menu opened downward past the card's bottom edge, so "Flag for cleaning"
  and "Take out of service" had never once been reachable from the UI. (2) With
  the clip removed and the menu opening upward it still did not fit: `w-44` is
  176px against a card of about 155px, so it overflowed the grid sideways and
  was clipped by the next ancestor that scrolled. Inline icon buttons fixed
  that but made a small card busy, with the actions wrapping onto a second row.
  (3) The menu is back behind the `⋮`, teleported to `<body>` and positioned
  against its button — `cardMenu()` in `app.js`, see the frontend rules above.
  Along the way the `:style` binding used for those coordinates turned out to
  be wiping `x-show`'s `display: none`, which left all 28 menus permanently
  rendered as invisible boxes at stale coordinates: that is the blank white
  panel that showed up in a screenshot. Positions are written imperatively now.
  Verified at 375, 768 and 1280px, on the first and last card in the grid:
  nothing is rendered while closed, the menu opens inside the viewport aligned
  to its button, every item is returned by `document.elementFromPoint()`, it
  follows the button on scroll and closes when the button leaves the screen,
  and Escape / outside click / a second click all dismiss it. The full round
  trip runs in the app: Available → Flag for cleaning → Cleaning → Mark clean →
  Available.
- ~~"In-house guests 9" looked wrong next to "Occupied 5"~~ — the same class of
  problem one screen over, and the number was right: five stays were in house
  holding nine people (1 + 3 + 1 + 1 + 3), while every other "in house" figure
  on the screens counts stays. Nothing said which unit either number was in. The
  dashboard tile is *Guests in house* now, with `5 stay(s) · … outstanding`
  underneath, and the front-desk column reads `5 stay(s) · 9 guest(s)`. The API
  figure (`DashboardStats.in_house_guests`, the sum of `guest_count`) was
  correct and is unchanged.
- ~~A room card and the front desk disagreed about how many guests were in a
  room~~ — the front desk showed room 306 as "Family Room · 1 guest(s)" while
  the rooms board showed the same room as "4 guest(s)". Neither number was
  wrong: the front desk prints the party on the booking (`adults + children`)
  and the card was printing the room type's capacity, both with the word
  "guest(s)". The card says `Sleeps 4` now — the wording `settings.html` and the
  booking form already used — and the occupant block carries the number a
  receptionist actually wants, the party in the room, with the booking reference
  moved onto its own line. No data was involved; nothing about occupancy,
  pricing or availability changed.
- ~~Marking an occupied room clean put it back on the sale floor~~ — room
  status and reservation status answer different questions, and nothing tied
  them together. Flagging an in-house room for cleaning and then pressing "Mark
  clean" set it to `AVAILABLE` while the guest was still checked in: the card
  showed a green AVAILABLE badge with the guest's name and check-out date right
  underneath it, and any attempt to sell the room failed on the overlap check
  with no explanation on screen. `RoomService.update_room` now resolves
  `AVAILABLE` to `OCCUPIED` whenever the room holds a checked-in stay, so
  cleaning an occupied room returns it to occupied — which is what housekeeping
  means by it. The rooms page reads the status back out of the response instead
  of echoing what it asked for, so the toast says "Occupied". Three rooms in the
  local demo database had already been left in that state and were repaired to
  `OCCUPIED`. Regression tests:
  `tests/test_reservations.py::test_cleaning_an_occupied_room_returns_it_to_occupied`
  and the three around it, which also pin the cases that must keep working —
  an empty room still becomes available, `PATCH /rooms/{id}` obeys the same
  rule, and a room whose guest has checked out is sellable again once cleaned.
- ~~The sidebar scrolled away and left an empty column~~ — the `<aside>` was
  `lg:static` inside a flex row, so it stretched to the height of the page
  (2023px against an 800px viewport). Scrolling the 28-card rooms grid put
  every one of the seven nav links off screen, leaving a blank white strip
  where the navigation should be. It is `lg:sticky lg:top-0 lg:h-screen` now,
  with its own overflow, so the navigation stays where it is at any scroll
  position. Two follow-ups on the same element, both so it cannot paint where it
  should not: a sticky flex child needs no horizontal offset, so `left` is
  `auto` from `lg` up (`lg:inset-y-auto lg:left-auto`), and the collapse
  animation is `transition-[width,transform]` instead of `transition-all` on a
  full-height sticky layer.
- ~~Room cards were cramped at desktop widths~~ — the grid went to five columns
  at `xl` (1280px), which left each card 184px wide: the room type name
  truncated to "Standard …" and the price wrapped onto its own line. Five
  columns start at `2xl` now, so a 1280px screen gets 233px cards and neither
  wraps.

### Audit follow-ups

- ~~A guest name containing markup permanently broke their invoice~~ —
  ReportLab parses `Paragraph` text as mini-XML, so a name like `<b>Ali` raised
  a parse error and returned a 500 every time that invoice was requested. All
  user-supplied text going into a `Paragraph` is escaped through `_esc()` in
  `app/services/invoice_service.py`. Table cells take plain strings and are not
  parsed, so they need no escaping.
- ~~Searching for `%` returned every row~~ — `%` and `_` are LIKE wildcards and
  the search term went into the pattern unescaped. `like_pattern()` in
  `app/repositories/base.py` neutralises them, and both call sites pass
  `escape=LIKE_ESCAPE`. This was never SQL injection — the queries are
  parameterised — but on a large table it was a full scan.
- ~~A guest could check out having paid the room charge but never the VAT~~ —
  `PaymentService.folio()`, `PaymentService.record()` and
  `ReservationService.balance()` all computed the amount owed as
  `Reservation.total_price - paid`, and `total_price` is stored net of tax.
  Once the pre-tax accommodation charge was paid, `balance_due` read `0.00`
  and check-out proceeded with the VAT never collected. All three now go
  through `app/services/pricing.py::total_due()`, the one place that adds VAT
  to what is owed. Found from a screenshot of the folio widget showing
  `Total 637.20`, `Paid 540.00`, `Balance due 0.00` — the arithmetic doesn't
  work unless tax is dropped from the balance calculation.

### Architecture & production-readiness audit of 2026-08-19 (closed same day)

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
  the room-502 incident recorded above**; widening `arrivals_on()` /
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
  class of defect as the two unit mismatches already fixed above — a number
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
  `_assert_may_set_rate`. Housekeeping keeps `CLEANING` and `AVAILABLE`.
- ~~`TRUSTED_HOSTS` defaulted to `*` and was exempt from the boot check~~ — the
  convention above says a security-relevant setting gets a check in
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
  and remains tracked in `SECURITY-TODO.md`.

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
