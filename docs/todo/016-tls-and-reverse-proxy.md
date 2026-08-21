# 016 — TLS and a reverse proxy

**Kind** operations · **Size** hours · **Depends on** nothing

## What is wrong

`docker-compose.yml` publishes port 8000 directly. Two things follow from that:

- The session cookie only gets its `secure` flag when `APP_ENV=production`, and
  HSTS only means anything over HTTPS — over plain HTTP the cookie travels in
  the clear.
- Without a proxy passing the real client address, the rate limiter sees the
  whole hotel as one IP. That makes the brute-force protection useless and lets
  one person's repeated typo lock everyone out.

## Fix

Caddy or nginx in front, terminating TLS, and `--forwarded-allow-ips=<proxy>` on
the app so it trusts that proxy's forwarded address and nothing else.

Two boxes of `docs/todo/001-pre-deploy-checklist.md` are the manual half of this
item; closing this one closes those.

## Done when

HTTPS serves, HTTP redirects to it, and two client addresses get two independent
rate-limit buckets.
