# Security — remaining work

What is left after the audits. The eleven gaps the first audit (2026-08) found
are closed (commit `89b3dcb`), as are the two follow-ups (the invoice PDF crash
and the LIKE wildcards) and, as of **2026-08-19**, all eleven findings of the
second review of 2026-08-17. The full history is in CLAUDE.md; this file tracks
only what has **not** been done yet.

The second review also confirmed a number of areas as clean — mass assignment
(all 30 handlers), role coverage, SQL injection (no `text()`, no f-string SQL),
XSS (no `|safe`; both `x-html` bindings read hard-coded icon constants), path
traversal, SSRF, error-handler leakage, cookie flags, the overlap/overbooking
logic, `Decimal` money precision, and PII scoping in `GuestSummary`. Those need
no work; do not re-audit them without a reason.

When an item is finished, delete it from here and move it into the "Fixed bugs"
section of CLAUDE.md, and add the regression test that keeps it fixed.

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
- [ ] **Point `RATE_LIMIT_STORAGE_URI` at Redis if there is more than one
      worker or container.** It defaults to `memory://`, which is per-process:
      with N processes the effective limit is N times what it says. The
      per-account lockout (`ACCOUNT_LOCK_AFTER_FAILURES`) counts in-process for
      the same reason and has the same caveat — see section 3.
- [ ] **Run `alembic upgrade head`.** `create_all` only runs in development.
- [ ] **Never run `seed.py` against the production database.** It contains
      fixed demo passwords (`Admin1234`, `Manager1234`, `Reception1234`), and
      because it writes to the model directly it bypasses the new password
      policy — those passwords can no longer be created through the API.

---

## 2. Hardening carried over from the 2026-08 audit

### 2.1 Remove `unsafe-inline` and `unsafe-eval` from the CSP

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

**Note (2026-08-17).** The design-system work moved the shared component classes
into a `<style type="text/tailwindcss">` block in `base.html`, which the CDN
compiles at runtime. When Tailwind moves to a build step, that block becomes a
real `@layer components` section in the compiled stylesheet — it is a
copy-paste move, not a rewrite, but do not forget it.

---

## 3. Shared state the rate limiting still needs

Both controls now exist and both count in one process:

- The per-IP limiter (`app/core/ratelimit.py`) reads
  `RATE_LIMIT_STORAGE_URI`, which defaults to `memory://`. Setting it to
  `redis://…` is all that is needed — `slowapi` handles the rest.
- The per-account lockout (`FailedLoginTracker`, ten consecutive failures then
  fifteen minutes) keeps its counters in a plain dict, so a second instance
  keeps its own. Moving it to the same Redis is the matching change, and it has
  to keep answering a locked address exactly as it answers a wrong password —
  otherwise it becomes the account-enumeration oracle that the identical login
  message exists to prevent.

Neither is a live exploit on a single instance, which is why this ranks below
section 2.

---

## 4. Longer term

- **Audit log.** Attribution now exists at the points where money moves or is
  given up: `Reservation.created_by_id` and `waived_by_id`,
  `Payment.recorded_by_id` (on the payment and on the refund counter-entry).
  What is still missing is a before/after trail for ordinary edits — who
  changed a price or a date, and what it was before. A separate `audit_log`
  table: actor, action, object, before/after, timestamp. In a system that
  touches money, that log is the only argument available when something is
  disputed.
- **Two-factor authentication.** At least for the admin and manager roles
  (TOTP).
- **Shorten the token lifetime.** `ACCESS_TOKEN_EXPIRE_MINUTES` is still 720
  (12 hours). Sign-out now revokes tokens through the `tv` claim, so the
  window only matters for a token stolen from a session nobody signs out of —
  but a front-desk shift is not 12 hours long.
- **Replace `passlib`.** `passlib` 1.7.4 is no longer actively maintained, and
  it is the reason `bcrypt` is pinned to 4.0.1 (it breaks with 4.1+).
  Alternatives: the `bcrypt` library directly, or `argon2-cffi`.
- **Dependency scanning in CI.** `pip-audit` or Dependabot — the `python-jose`
  CVEs sat there until the audit, and could have been caught automatically.
