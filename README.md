# Grand Aurora — Hotel Guest Management System

A production-shaped hotel front-office system: register guests, manage room
inventory, take bookings, run check-in/check-out, settle accounts and report on
performance.

Built with **FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL/SQLite · Jinja2 ·
TailwindCSS · Alpine.js · Chart.js**.

---

## Quick start

Two commands and you have a working hotel with 45 days of history.

```bash
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
```

```bash
python seed.py && python run.py
```

Then open **http://127.0.0.1:8000**.

| Role | Email | Password |
| --- | --- | --- |
| Administrator | `admin@grandaurora.az` | `Admin1234` |
| Manager | `manager@grandaurora.az` | `Manager1234` |
| Receptionist | `reception@grandaurora.az` | `Reception1234` |

The login screen has one-click buttons for each of these.

> SQLite is the default, so nothing else needs installing. Point
> `DATABASE_URL` at PostgreSQL when you want to.

---

## Where the project stands

Two security audits and one functional review have been through this code. As of
**2026-08-19** everything they found is fixed, each with a regression test.

| Question | Where it is answered |
| --- | --- |
| What is fixed, and what broke in the first place | "Fixed bugs" in [`CLAUDE.md`](CLAUDE.md) |
| What is still open on security | [`SECURITY-TODO.md`](SECURITY-TODO.md) |
| What is still open functionally | [`BUGS-TODO.md`](BUGS-TODO.md) |
| The rules this code must not break | "Conventions" and "Security rules" in [`CLAUDE.md`](CLAUDE.md) |
| How a change came to be | `git log` — the history is part of the documentation |

Everything written down here — documentation, commit messages, code comments —
is in English. Commits before 2026-08-19 are in Azerbaijani; that is history,
not the convention.

The short version of what is left: the CSP still needs `unsafe-inline` and
`unsafe-eval` until Tailwind, Alpine and Chart.js are vendored with a build
step; rate limiting counts in one process until `RATE_LIMIT_STORAGE_URI` points
at Redis; there is no audit trail for ordinary edits and no two-factor
authentication; and the pre-deployment checklist in `SECURITY-TODO.md` is
configuration nobody can do for you.

---

## What it does

**Front desk**
- Search any booking by reference, guest name, phone or room number
- One-click check-in; check-out that refuses to close an unpaid account unless
  a supervisor confirms
- Live folio drawer: itemised bill, take payment, issue the invoice PDF

**Reservations**
- Four-step booking wizard: guest → dates → room → confirm
- Availability search that prices the whole stay as you pick
- Walk-in flow that registers the guest and books them in one request
- Modify, cancel and no-show handling, each with its own guard rails

**Rooms**
- Colour-coded grid showing who is in each room and who arrives next
- Housekeeping states: available / occupied / cleaning / maintenance
- A room under maintenance disappears from availability entirely

**Guests**
- Register with document validation; duplicate documents are rejected and the
  existing guest is offered instead
- Search across name, phone, email and document number
- Per-guest stay history

**Money**
- Payments in cash, card, transfer or online; overpayment is rejected
- VAT applied on the invoice; PDF generated server-side with ReportLab
- Outstanding balance tracked per stay and rolled up on the dashboard

**Reports** (manager and admin only)
- Revenue and occupancy by day, ADR, room-type performance, payment mix
- Any date range, CSV export, print stylesheet

---

## The rule that matters

A room is never sold twice for the same night. Two stays overlap when each
starts before the other ends:

```
new.check_in < existing.check_out  AND  new.check_out > existing.check_in
```

The comparisons are **strict**, which makes same-day turnover legal — one guest
leaves at noon, another arrives at 14:00, no false conflict. The check runs in
`RoomRepository.is_available()` and is enforced on every create *and* every
modification, excluding the reservation being edited so moving a booking's dates
doesn't clash with itself.

Only `pending`, `confirmed` and `checked_in` block the calendar. Cancelling
frees the room immediately — but cancelling a stay that is already **checked in**
is a manager action, and it is refused while the guest still owes money unless
the manager writes the balance off explicitly. Cancelling an in-house stay
removes its nights from occupancy and its debt from the ledger, so it cannot be
a quiet front-desk shortcut.

A booking whose dates have passed without a check-in, and a guest whose
check-out date has passed, both still hold their room. Neither is hidden: the
front desk, the dashboard, the rooms board and the reservations list all show
them, labelled with how many days overdue they are.

There is a test for every overlap shape — see
[`tests/test_reservations.py`](tests/test_reservations.py).

---

## Layout

```
app/
├── core/            config, async engine, JWT + bcrypt, exceptions, dependencies
├── models/          SQLAlchemy tables (users, guests, room_types, rooms,
│                    reservations, payments, invoices)
├── schemas/         Pydantic v2 request/response models
├── repositories/    data access — every query lives here
├── services/        business rules — overbooking, pricing, lifecycle, reports
├── routers/
│   ├── api/         JSON API under /api/v1
│   └── web.py       server-rendered pages
├── templates/       Jinja2 (base + 8 pages + partials)
├── static/          app.css, app.js (API client, formatters, toasts)
└── main.py          app assembly, middleware, error handlers

alembic/             migrations
tests/               98 tests covering auth, security, booking rules, money, lifecycle
seed.py              demo hotel: 28 rooms, 15 guests, 175 reservations
```

Requests flow **router → service → repository → database**. Routers never touch
the ORM; services never build SQL. That's what makes the booking rules testable
in isolation.

---

## Roles

| | Receptionist | Manager | Admin |
| --- | --- | --- | --- |
| Bookings, check-in/out, payments | yes | yes | yes |
| Guests, housekeeping status | yes | yes | yes |
| Reports, refunds, rate override, no-show | — | yes | yes |
| Room inventory, delete guests | — | yes | yes |
| Staff accounts | — | — | yes |

Enforced server-side by the `StaffUser` / `ManagerUser` / `AdminUser`
dependencies — the UI hiding a button is a convenience, not the control.

---

## API

Interactive docs at **http://127.0.0.1:8000/api/docs** (development only — the
schema is not exposed in production).

```
POST   /api/v1/auth/login                        sign in (JWT + httpOnly cookie)
GET    /api/v1/rooms/availability                what's free, priced for the stay
POST   /api/v1/reservations                      book (409 on any clash)
POST   /api/v1/reservations/walk-in              register guest + book at once
GET    /api/v1/reservations/front-desk           today's arrivals/departures/in-house
POST   /api/v1/reservations/{id}/check-in
POST   /api/v1/reservations/{id}/check-out       ?allow_outstanding_balance=true (manager+, recorded)
POST   /api/v1/reservations/{id}/cancel          manager+ once the guest is checked in
POST   /api/v1/reservations/{id}/no-show         manager+; resolves a booking nobody arrived for
POST   /api/v1/payments                          take money
POST   /api/v1/payments/{id}/refund              manager+; writes a counter-entry, never edits the original
GET    /api/v1/payments/folio/{id}               itemised bill
POST   /api/v1/invoices/reservation/{id}         issue the invoice (this is the write)
GET    /api/v1/invoices/reservation/{id}/pdf     render an issued invoice (404 if none — a GET never writes)
GET    /api/v1/reports/summary                   ?start=&end=  (manager+)
```

Errors are uniform, so the frontend renders them without special cases:

```json
{ "error": { "code": "conflict",
             "message": "Room 205 is already booked for part of 2026-08-14 → 2026-08-17.",
             "details": {} } }
```

---

## Testing

```bash
python -m pytest
```

98 tests: authentication and role boundaries, every overlap shape, capacity and
date validation, the full check-in → pay → check-out lifecycle, VAT and balance
arithmetic, invoice idempotency, guest document rules. Each test runs against a
fresh in-memory SQLite database. The suite takes a few minutes — bcrypt is
deliberately slow, and most tests sign in.

`tests/test_security.py` and `tests/test_config.py` are regression tests for the
2026-08 security audit and the 2026-08-17 review — rate limiting and the
per-account lockout, privilege escalation on the rate override, session
invalidation on password change *and* on sign-out, last-admin lockout, password
policy, security headers, the production configuration guard, the recorded
manager waiver, guest deletion with financial history, and the read-only invoice
PDF route.

`tests/test_payments.py` covers the money arithmetic that has been wrong twice:
VAT is part of what the guest owes, the dashboard's outstanding balance agrees
with the folio, a refund leaves the payment it reverses on the record, and the
overpayment ceiling applies whatever status the client sends.

---

## Deployment

```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
```

```bash
docker compose up --build
```

Brings up PostgreSQL, runs `alembic upgrade head`, serves the app on port 8000.

Compose runs with `APP_ENV=production`, which refuses to start on development
defaults — a missing or shipped `SECRET_KEY`, `DEBUG=true`, or `CORS_ORIGINS=*`
all fail at boot rather than silently serving traffic. The interactive API docs
are also disabled in production. See [`SECURITY-TODO.md`](SECURITY-TODO.md) for
the full pre-deployment checklist.

Migrations, when you change a model:

```bash
python -m alembic revision --autogenerate -m "what changed"
```

```bash
python -m alembic upgrade head
```

`APP_ENV=development` creates tables on boot for convenience. In production it
does not — Alembic owns the schema.

---

## Configuration

Everything lives in `.env` (see `.env.example`). The values worth knowing:

| Key | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./hotel.db` | `postgresql+asyncpg://…` for Postgres |
| `SECRET_KEY` | dev placeholder | **must** change for production |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | session length; signing out revokes the token before this |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | per-process — point at `redis://…` with more than one worker |
| `ACCOUNT_LOCK_AFTER_FAILURES` | `10` | consecutive failed logins before the account is locked |
| `ACCOUNT_LOCK_MINUTES` | `15` | how long that lock lasts |
| `TAX_RATE` | `0.18` | VAT on invoices — part of what the guest owes, not an extra |
| `CURRENCY` | `AZN` | shown throughout the UI and on invoices |

Generate a real key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Security notes

- Passwords hashed with bcrypt; the 72-byte bcrypt limit is rejected explicitly
  rather than silently truncated
- JWT in an httpOnly, SameSite=Lax cookie (`Secure` when `APP_ENV=production`)
- Login errors are identical for unknown email and wrong password — and both
  pay for one bcrypt round, so response time does not leak which addresses exist
- Sign-in is rate limited per IP and locked per account after repeated failures;
  a locked account answers exactly like a wrong password
- Sessions are revocable: tokens carry a fingerprint of the password hash and a
  token version, so changing a password or signing out invalidates tokens that
  have not expired yet
- Money is authorised in the service layer, not in the UI: overriding a nightly
  rate, checking a guest out with a balance owing, and cancelling an in-house
  stay all require a manager, and any balance given up is recorded against the
  reservation with the amount, the time and the manager
- Payments are append-only — a refund is a counter-entry pointing at the
  settled payment, which is never edited, so the record of cash received cannot
  be erased
- A GET never writes: the invoice PDF route renders an invoice that has been
  issued and 404s otherwise, because a `SameSite=Lax` cookie travels with a
  mailed link
- All queries go through the ORM — no string-built SQL, and search terms have
  their LIKE wildcards escaped
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, a CSP and
  `Cache-Control: no-store` on every non-static response
- The last active administrator cannot be deactivated or demoted

Before going live: change `SECRET_KEY`, set `APP_ENV=production`, put it behind
HTTPS, and replace the seeded demo accounts.

---

## Notes on the frontend

Server-rendered Jinja2 with Alpine.js for interactivity — no build step, no
bundler. Tailwind and Alpine load from CDN, so the app is one `python run.py`
away from working.

Dark mode is applied before first paint (no white flash), persists in
`localStorage`, and the charts redraw with theme-appropriate axis colours when
you toggle it. Every list has a real empty state, every async area has a
skeleton rather than a spinner, and every destructive action goes through a
confirmation dialog.
