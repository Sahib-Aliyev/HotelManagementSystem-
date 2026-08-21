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
- Hiding a button in the UI is not a role check. Every endpoint must enforce it
  server-side too, via the dependencies in `app/core/deps.py`.

## Invariants

The rules whose violation is silent and costs money. Each line is the short
form; the rule file named after it carries the full version and the reasoning,
and loads when you open a file it applies to.

- Money arithmetic lives only in `app/services/pricing.py` → money-and-billing
- What a guest owes is `total_due()`, never `Reservation.total_price` → money-and-billing
- Payments are append-only; sum through `is_cash_movement()` / `signed_amount()` → money-and-billing
- Forgiving a balance needs a manager and records `waived_amount/at/by_id` → money-and-billing
- Revenue is accrual, cash is cash; never divide one by the other → money-and-billing
- Selling a room and occupying it are different questions → reservations-and-rooms
- A room's housekeeping status may not contradict the calendar → reservations-and-rooms
- `X | None` is optional on input, not nullable → api-and-schemas
- State never travels in a query string → api-and-schemas
- The role belongs to the state change, not to the route → services-runtime
- PostgreSQL is the supported target; SQLite cannot express `no_double_booking` → docs/LIMITATIONS.md
- Frontend calls go through `api()`; the UI vocabulary is the component classes in `base.html` → frontend

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
- A hook refuses a commit thinner than this, rather than trusting whoever is
  working to remember → `docs/AGENT-AUTOMATION.md`

## Automation

`.claude/settings.json` wires three hooks (schema drift after a model edit, the
commit-message gate, `ruff format` after writing Python) and
`.claude/skills/finding/` carries the `/finding` procedure for closing an open
item. A hook or a skill links to the rule it serves and never restates it; what
each one enforces and why is in `docs/AGENT-AUTOMATION.md`.

## Rule files

`.claude/rules/*.md` carry the detail, scoped by `paths:` so each one loads only
when you open a file it governs. One owner per area — put a new rule in the file
that owns its area rather than restating it here.

| Area | Rule file |
| --- | --- |
| templates, static assets | `.claude/rules/frontend.md` |
| pricing, payments, invoices, reports | `.claude/rules/money-and-billing.md` |
| reservations, rooms | `.claude/rules/reservations-and-rooms.md` |
| schemas, API routers | `.claude/rules/api-and-schemas.md` |
| service-layer runtime, guest PII | `.claude/rules/services-runtime.md` |
| migrations, models | `.claude/rules/migrations.md` |
| tests, CI | `.claude/rules/tests.md` |

## Open work and history

- Security findings and the pre-deployment checklist: `SECURITY-TODO.md`
- Functional defects, and decisions deliberately not taken: `BUGS-TODO.md`
- Limitations that are accepted rather than open: `docs/LIMITATIONS.md`
- The sequence from here to a production deployment: `docs/ROADMAP.md`
- The hooks and skills that exist, the two skills still worth writing, and the
  rule files both must link to rather than restate: `docs/AGENT-AUTOMATION.md`
- How each fixed bug happened, with the reproductions and the measured figures:
  `docs/history/` — start at `docs/history/README.md`
- When an item is finished, delete it from the TODO file and record it in
  `docs/history/fixed-bugs.md` with the regression test that keeps it fixed.

<!-- Do not add `@path` imports to this file. Imports expand at launch, so
     importing the rule files or the history would put all 753 original lines
     back into every session's context, which is what this split undid. The rule
     files are discovered through their `paths:` frontmatter instead. -->
