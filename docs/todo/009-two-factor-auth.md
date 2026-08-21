# 009 — Two-factor authentication for admin and manager

**Kind** security · **Size** days · **Depends on** nothing

## What is wrong

A stolen or guessed manager password is enough to override a nightly rate, waive
a balance, refund a payment or anonymise a guest. A stolen admin password is
enough to create staff accounts. Password plus rate limiting plus a per-account
lockout is what stands in front of all of that today.

Receptionists are a different case: TOTP on a shared front-desk machine during a
shift change costs more than it protects, which is why this is scoped to the two
roles that can move money.

## Fix

TOTP for the `admin` and `manager` roles: a secret per user, enrolment with a QR
code, and verification as a second step after the password check.

The parts that need care rather than typing:

- **The endpoint is an authentication endpoint**, so it needs a rate limit —
  the rule and its silent failure mode are a **Security rule** in `CLAUDE.md`.
- **Recovery codes**, or an admin who loses their phone locks themselves out of
  a system where the last active admin cannot be demoted or deactivated
  (`AuthService` guards both paths).
- **The token claims.** Whatever marks a session as second-factor-verified has
  to survive alongside `pwf` and `tv`, not replace either.

## Done when

A manager and an admin cannot complete a sign-in without the second factor, a
receptionist is unaffected, a recovery code works exactly once, and the enrolment
endpoint is rate limited with a test that proves the limit fires.
