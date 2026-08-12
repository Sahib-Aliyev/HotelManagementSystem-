# Security — remaining work

What is left after the 2026-08 audit. The eleven gaps the audit found are
already closed (commit `89b3dcb`; the history is in CLAUDE.md) — this file
tracks the work that has **not** been done yet.

When an item is finished, delete it from here and move it into the "Fixed bugs"
section of CLAUDE.md.

---

## 1. Before deploying

No code changes — these are configuration and environment concerns.
`APP_ENV=production` checks a few of them at boot and lets the rest through
silently, so walk the list by hand.

- [ ] **Generate a `SECRET_KEY`.** `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
      Production will not start on the shipped key, but if the key ever leaks,
      anyone can forge any user's session. Rotating the key also invalidates
      every existing session.
- [ ] **Set `CORS_ORIGINS` to the real domain.** `*` is rejected at boot because
      the cookie is credentialed, but a wrong domain is not.
- [ ] **Set `TRUSTED_HOSTS` to the real hostnames.** The default is `*`, which
      disables the Host header check entirely.
- [ ] **Serve over HTTPS.** The session cookie only gets its `secure` flag and
      the HSTS header when `APP_ENV=production`; over plain HTTP the cookie
      travels in the clear.
- [ ] **Forward the real client IP if there is a proxy in front.** Run uvicorn
      with `--proxy-headers --forwarded-allow-ips=<proxy-ip>`. Without this the
      rate limiter sees **every user as one IP**, which both makes the
      brute-force protection useless and lets one person's typo lock out the
      whole hotel.
- [ ] **Run `alembic upgrade head`.** `create_all` only runs in development.
- [ ] **Never run `seed.py` against the production database.** It contains
      fixed demo passwords (`Admin1234`, `Manager1234`, `Reception1234`), and
      because it writes to the model directly it bypasses the new password
      policy — those passwords can no longer be created through the API.

---

## 2. Requires code changes (in priority order)

### 2.1 Invoice PDF crashes on some guest names — *confirmed*

**Problem.** `app/services/invoice_service.py:140` passes the guest's name,
phone and email straight into a ReportLab `Paragraph`. `Paragraph` treats its
text as a mini-XML markup language, so a name containing something that looks
like an unclosed tag raises a parse error and returns a 500:

```
'<b>Bold Guest'  ->  ValueError: paragraph text '<para><b>Bold Guest<br/>+994</para>' caused exception
```

`&` and a bare `<` are fine — only tag-shaped constructs break it.

**Why it matters.** Severity is low, since staff enter the name rather than an
outside user, but the effect is persistent: once such a name is in the
database, that guest's invoice can **never** be generated again, and the reason
is not obvious without reading the logs.

**Fix.** Escape all user-supplied text on its way into the PDF:

```python
from xml.sax.saxutils import escape
Paragraph(f"{escape(reservation.guest.full_name)}<br/>...", value)
```

The same applies to `line.label` and `line.detail` in `folio.lines`, which are
built from the room number and room type name.

**Test.** In `tests/test_security.py`: create a guest whose name contains
`<b>`, download the invoice PDF, expect 200.

### 2.2 Remove `unsafe-inline` and `unsafe-eval` from the CSP

**Problem.** The CSP in `app/main.py` still allows both, because Tailwind,
Alpine.js and Chart.js load from CDNs and Tailwind's browser build compiles
styles at runtime (which needs `eval`). These two concessions eat most of the
CSP's value against XSS.

**Fix.** Vendor all three libraries into `app/static/vendor/`. Tailwind needs a
build step for this — the CLI-compiled CSS, not the CDN build. Then:

- `script-src 'self'` (drop the CDN domains)
- `style-src 'self'` — clean up any inline `style=` attributes first
- Alpine attributes like `x-data` do not violate CSP, but Alpine itself needs
  `unsafe-eval` to evaluate expressions. Use Alpine's **CSP build**
  (`@alpinejs/csp`), otherwise this item stays half-finished.

**Note.** This also fixes a related exposure: if any of the three CDNs were
compromised today, every session in the hotel could be stolen. Vendoring
removes that dependency completely.

### 2.3 Move rate limiting to shared storage

**Problem.** The limiter in `app/core/ratelimit.py` counts in memory
(`MemoryStorage`). That works for a single instance; as soon as there are two
or more uvicorn workers or containers, each keeps its own counter and the
effective limit is multiplied by the worker count.

**Fix.** `Limiter(storage_uri="redis://...")`. `slowapi` supports this
directly. Add `RATE_LIMIT_STORAGE_URI` to `.env` and default it to in-memory so
development still needs no setup.

### 2.4 Count failed logins per account as well

**Problem.** The limit is currently per-IP only. A botnet (ten attempts per IP)
can still run a slow brute force against a single account.

**Fix.** Add a per-email counter alongside the IP limit — for example, lock the
account for 15 minutes after ten consecutive failures. Careful: the lockout
response must look identical for an account that does not exist, otherwise the
account-enumeration leak closed in the audit comes straight back.

### 2.5 LIKE wildcards in search

**Problem.** `app/repositories/reservation_repo.py:64` and the guest search put
user text directly into a `LIKE` pattern. Someone typing `%` matches every row.
This is **not** SQL injection — the query is parameterised — just surprising
results and a slow query on a large database.

**Fix.** Escape `%`, `_` and `\` before building the pattern and use
`.like(pattern, escape="\\")`.

---

## 3. Longer term

- **Audit log.** Only `Reservation.created_by_id` is stored today. Who changed
  a price, who cancelled a reservation, who issued a refund — none of it is
  tracked. In a system that touches money, that log is the only argument
  available when something is disputed. A separate `audit_log` table: actor,
  action, object, before/after, timestamp.
- **Two-factor authentication.** At least for the admin and manager roles
  (TOTP).
- **Replace `passlib`.** `passlib` 1.7.4 is no longer actively maintained, and
  it is the reason `bcrypt` is pinned to 4.0.1 (it breaks with 4.1+).
  Alternatives: the `bcrypt` library directly, or `argon2-cffi`.
- **Dependency scanning in CI.** `pip-audit` or Dependabot — the `python-jose`
  CVEs sat there until the audit, and could have been caught automatically.
