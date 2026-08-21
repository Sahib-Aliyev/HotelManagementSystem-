# 004 — One shared store for both rate-limit counters

**Kind** security · **Size** hours · **Depends on** nothing

## What is wrong

Both brute-force controls count **in one process**, so a second worker or
container keeps its own count and the effective limit is multiplied by the number
of instances.

- The per-IP limiter (`app/core/ratelimit.py`) reads `RATE_LIMIT_STORAGE_URI`,
  which defaults to `memory://`.
- The per-account lockout (`FailedLoginTracker`, ten consecutive failures then
  fifteen minutes) counts in-process with no setting at all.

Neither is a live exploit on a single instance, which is why this ranks below
002 — but it is the one item on this list that silently gets *worse* the moment
the deployment is scaled, which is also when nobody is thinking about it.

## Fix

- The limiter needs nothing but `RATE_LIMIT_STORAGE_URI=redis://…`; `slowapi`
  handles the rest.
- `FailedLoginTracker` needs the same store. It must keep answering a locked
  address exactly as it answers a wrong password — otherwise it becomes the
  account-enumeration oracle that the identical login message exists to prevent.

The store is already **bounded and expiring** as of the 2026-08-19 audit, so the
unbounded-growth problem is closed; only the sharing problem is open.

## Done when

Two workers share one lockout: locking an account through one instance and being
refused by the other, with the refusal indistinguishable from a wrong password.
`tests/test_security.py` already pins the indistinguishability — keep it passing.
