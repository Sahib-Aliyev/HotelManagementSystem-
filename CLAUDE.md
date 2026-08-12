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
  never the tax — see "Fixed bugs".

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

## Known limitations

Open security work and the pre-deployment checklist live in a separate file:
**`SECURITY-TODO.md`**. What follows is limitations that are deliberately
accepted.

- No email notifications, and only a single currency (`CURRENCY` in `.env`).
- The CSP still allows `unsafe-inline` and `unsafe-eval`, because Tailwind,
  Alpine and Chart.js load from CDNs and Tailwind compiles styles in the
  browser. Vendoring those three files is what allows a strict CSP.
- Rate limiting is per-IP and in-memory: behind a proxy the real client IP must
  be forwarded, and more than one instance needs shared storage such as Redis.
- No audit log — apart from `created_by_id`, who changed a reservation is not
  recorded.
- No two-factor authentication.

## Git / commit rule

- Write a **broad and detailed description** on every commit before pushing:
  what changed, why it changed, which files it touched. A single line like
  "fix bug" is not enough.
- Format: a short summary on the first line, a blank line, then bullets with
  the reasoning and details.
- The goal: someone reading the history later (Sahib or Claude) should
  understand what was done and why from the message alone, without re-reading
  the code.
- Commit messages themselves stay in Azerbaijani, matching the existing
  history. Documentation (`*.md`) is written in English.

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
