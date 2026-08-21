# Route to production

What stands between "runs in `docker compose`" and "a hotel could use this",
ordered by what would hurt most on the first real night rather than by how
interesting it is. Each stage names its own *done when*, so it can be closed
rather than admired.

Open defects live in `SECURITY-TODO.md` and `BUGS-TODO.md`; accepted limitations
in `docs/LIMITATIONS.md`. This file is only the sequence.

## Stage 0 — the things whose absence is unrecoverable

1. **Backups and a tested restore.** PostgreSQL lives in a named volume with no
   dump schedule and no restore procedure, and this is tracked in neither TODO
   file. A hotel losing its folio history is an incident, not a bug. Nightly
   `pg_dump` to off-host storage, 7 daily plus 4 weekly, and a restore drill
   written down in `docs/runbook.md`.
   *Done when:* a restore into a scratch database reproduces the reservation and
   payment counts, and the drill has actually been run once.
2. **TLS and a reverse proxy.** `docker-compose.yml` publishes 8000 directly. The
   session cookie only gets its `secure` flag and HSTS only means anything over
   HTTPS. Put Caddy or nginx in front, terminate TLS, and pass
   `--forwarded-allow-ips=<proxy>` so the rate limiter sees real client
   addresses instead of throttling the whole hotel as one.
   *Done when:* HTTPS serves, HTTP redirects, and two client IPs get two
   independent rate-limit buckets.
3. **Walk the pre-deploy checklist** in `SECURITY-TODO.md` §1 — it is already
   written. Open boxes: `SECRET_KEY`, `CORS_ORIGINS`, HTTPS,
   `--forwarded-allow-ips`, `RATE_LIMIT_STORAGE_URI`, `alembic upgrade head`,
   `POSTGRES_PASSWORD`, and never running `seed.py` against production.

## Stage 1 — being able to see what happened

4. **Request IDs and structured logs.** Today a 500 in production leaves a stack
   trace with nothing tying it to a user, a reservation or a request. Middleware
   that stamps an id, logs one JSON line per request (method, path, status,
   duration, user id, request id) and returns the id in the error body so a
   receptionist can quote it.
   *Done when:* a deliberately broken request is findable in the logs by the id
   shown on screen.
5. **Error tracking and an uptime check.** Sentry or equivalent for exceptions;
   an external monitor on `/health`, which already answers 503 when the database
   is unreachable.
   *Done when:* stopping the database container produces both a 503 and an alert.

## Stage 2 — the audit log

6. The highest-value missing piece, named in `SECURITY-TODO.md` §4 and
   `BUGS-TODO.md`, and the reason three findings (cancelling a stay, refunding a
   payment, waiving a balance) were worse than they had to be. Attribution
   exists wherever money moves — `created_by_id`, `recorded_by_id`,
   `waived_by_id` — but there is no before/after trail for ordinary edits: a
   price change or a date change is attributed to nobody. One table
   (`actor, action, object, before, after, at`), written from the service layer,
   which is already the single choke point every write passes through.
   *Done when:* changing a rate, a date and a room each leave a row, and a stay
   can show who changed what.

## Stage 3 — more than one process

7. **Redis for both counters.** `RATE_LIMIT_STORAGE_URI` already exists for the
   per-IP limiter; `FailedLoginTracker` needs the same treatment and must keep
   answering a locked address exactly as it answers a wrong password, or it
   becomes the account-enumeration oracle the identical login message exists to
   prevent.
   *Done when:* two workers share one lockout — locking through one and being
   refused by the other.
8. **Then run two workers** behind the Stage 0 proxy and re-run
   `tests/test_double_booking_pg.py` against the real deployment. The exclusion
   constraint is what makes concurrency safe, so prove it in situ rather than
   trusting the single-process case.

## Stage 4 — close the CSP hole properly

9. **Move the Alpine components out of `<script>` blocks** into
   `app/static/js/pages/*.js`. `BUGS-TODO.md` records the dependency:
   `unsafe-inline` cannot leave `script-src` while the components live in the
   HTML. They also become lintable and testable for the first time — the last
   three UI defects were all in that code.
10. **Vendor Tailwind (the CLI build, not the CDN), Alpine's CSP build and
    Chart.js**, then tighten to `script-src 'self'` and `style-src 'self'`.
    *Done when:* no CSP violations in the console, and `tests/test_security.py`
    asserts the header carries no `unsafe-*`.

## Stage 5 — what a hotel asks for next

In the value order already scoped under "Product gaps" in `BUGS-TODO.md`:

- **Room move and stay extension as first-class operations.** The two most
  common front-desk actions after check-in, today done by `PATCH`-ing `room_id`
  or `check_out_date`, which silently re-prices and records nothing.
- **Rate plans.** `nightly_rate` is one number per booking, so seasonality means
  a manager overriding by hand — which is most of why the manager-only rate
  override exists at all.
- **Cancellation policy and deposits.** Every cancellation is currently free.
- **Email notifications.** Confirmation and receipt: the one integration a guest
  actually notices.

## Cross-cutting hygiene

- **A lock file with hashes** (`uv` or `pip-tools`). `requirements.txt` pins
  direct dependencies but not transitive ones; `pip-audit` already runs in CI.
- **Replace `passlib`** — unmaintained, and the reason `bcrypt` is pinned to
  4.0.1.
- **Shorten `ACCESS_TOKEN_EXPIRE_MINUTES`** from 720. Sign-out revokes properly
  now, but a front-desk shift is not twelve hours long.
- **A load test of the front-desk flow**, so the threadpool fix and the N+1 work
  have numbers attached rather than claims.
- **State the test count in one place, or not at all** — `README.md` currently
  says 98 in one place and 134 in another.
