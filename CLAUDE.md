# HotelManagementSystem

Hotel guest registration and reservation management system. FastAPI backend,
server-rendered Jinja2 + Alpine.js + TailwindCSS frontend. A learning /
portfolio project — there are no real hotel users; it runs on PostgreSQL or
SQLite.

## Commands

- Server (dev): `.venv\Scripts\python.exe run.py` → http://127.0.0.1:8000, API docs `/api/docs`
- Tests: `.venv\Scripts\python.exe -m pytest -v`
- A single test file: `.venv\Scripts\python.exe -m pytest tests/test_reservations.py -v`
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
- **The sidebar is `lg:sticky lg:top-0 lg:h-screen`, not `lg:static`.** As a
  static flex child it stretched to the height of the page, so scrolling a long
  list carried the whole navigation off screen and left an empty column behind.
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
  in-process too, with the same caveat.
- No audit log. Who took a payment (`recorded_by_id`), who refunded it (the
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
- ~~The sidebar scrolled away and left an empty column~~ — the `<aside>` was
  `lg:static` inside a flex row, so it stretched to the height of the page
  (2023px against an 800px viewport). Scrolling the 28-card rooms grid put
  every one of the seven nav links off screen, leaving a blank white strip
  where the navigation should be. It is `lg:sticky lg:top-0 lg:h-screen` now,
  with its own overflow, so the navigation stays where it is at any scroll
  position.
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
