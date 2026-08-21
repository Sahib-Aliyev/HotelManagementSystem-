<a id="security-audit-2026-08"></a>

# Security audit (2026-08)

Eleven gaps, all closed in commit `89b3dcb`. Index:
`docs/history/README.md`.

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
