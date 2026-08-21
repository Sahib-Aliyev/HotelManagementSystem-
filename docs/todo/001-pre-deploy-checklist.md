# 001 — Walk the pre-deployment checklist

**Kind** configuration · **Size** hours · **Depends on** nothing

No code changes. `APP_ENV=production` refuses to boot on a few of these and lets
the rest through silently, so the list has to be walked by hand once, on the
machine that will actually serve.

## The boxes

- [ ] **Generate a `SECRET_KEY`** — `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
      Production will not start on the shipped key, but if the key leaks anyone
      can forge any user's session. Rotating it invalidates every existing
      session, which is the point.
- [ ] **Set `CORS_ORIGINS` to the real domain.** `*` is rejected at boot because
      the cookie is credentialed; a *wrong* domain is not rejected.
- [ ] **Serve over HTTPS.** The session cookie only gets its `secure` flag and
      the HSTS header when `APP_ENV=production`; over plain HTTP it travels in
      the clear.
- [ ] **Forward the real client IP if a proxy is in front.** `compose` already
      passes `--proxy-headers`; add `--forwarded-allow-ips=<proxy-ip>`. What goes
      wrong without it is in `docs/todo/016-tls-and-reverse-proxy.md`, which is
      the same problem stated as work.
- [ ] **Point `RATE_LIMIT_STORAGE_URI` at Redis** if there is more than one
      worker or container — see 004, which is the same problem stated as work.
- [ ] **Run `alembic upgrade head`.** `create_all` only runs in development.
- [ ] **Set `POSTGRES_PASSWORD`.** `docker-compose.yml` demands it rather than
      shipping `hotel`/`hotel`, and no longer publishes 5432 to the host.
- [ ] **Never run `seed.py` against the production database.** It contains fixed
      demo passwords and writes to the model directly, bypassing the password
      policy — those passwords can no longer be created through the API.

`TRUSTED_HOSTS` used to be on this list and is not any more: production refuses
to boot on the default `*`, `docker-compose.yml` sets real hostnames, and
`config.py::_refuse_unsafe_production` enforces it.

## Done when

Every box above is ticked on the target machine, and the app is serving over
HTTPS with two client addresses getting two independent rate-limit buckets.
