# 007 — Replace `passlib`

**Kind** dependency · **Size** hours · **Depends on** nothing

## What is wrong

`passlib` 1.7.4 is no longer actively maintained, and it is the reason `bcrypt`
is pinned to 4.0.1 — `passlib` breaks with 4.1 and later. So one unmaintained
package is holding a security-relevant dependency two years behind.

## Fix

Either the `bcrypt` library directly, or `argon2-cffi`. Whichever is chosen, the
hashing entry points are already isolated in `app/core/security.py` and every
request-path caller goes through the async wrappers — the rule for that is in
`.claude/rules/services-runtime.md`, and the replacement has to keep it: the new
library is still synchronous and CPU-bound.

Two things must not break:

- The 72-byte bcrypt limit is currently rejected explicitly rather than silently
  truncated. A different algorithm changes that check; it does not remove the
  need for one.
- Tokens carry a fingerprint of the password hash (`pwf`). Changing the hash
  format changes every fingerprint, so every existing session is invalidated on
  deploy. That is acceptable, but it should be a decision rather than a surprise.

Existing hashes have to keep verifying, or the demo accounts and any real
password stop working — plan for verify-old / rehash-on-login if the algorithm
changes.

## Done when

`passlib` is out of `requirements.txt`, `bcrypt` is unpinned (or gone),
`tests/test_auth.py` and `tests/test_security.py` pass unchanged, and an
account created before the change can still sign in.
