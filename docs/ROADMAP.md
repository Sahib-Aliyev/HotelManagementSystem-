# Route to production

What stands between "runs in `docker compose`" and "a hotel could use this", in
the order that limits the damage of a first real night rather than the order that
is most interesting to build.

**This file is only the sequence and the reasoning behind it.** Each item is
described in exactly one place, `docs/todo/`, and named here by number; accepted
limitations are in `docs/LIMITATIONS.md`.

## Stage 0 — the things whose absence is unrecoverable

**015** backups and a tested restore · **016** TLS and a reverse proxy · **001**
the pre-deployment checklist

Losing the folio history is an incident rather than a bug, and it is the only
failure on this whole list that cannot be repaired afterwards — so it goes first,
before anything that merely makes the system better. TLS is next because the
session cookie and the rate limiter are both wrong without it, and the checklist
is last of the three because it is the manual half of the other two.

## Stage 1 — being able to see what happened

**017** request IDs and structured logs · **018** error tracking and an uptime
check

Everything after this stage is easier to diagnose and harder to get wrong once a
failure can be traced from a screen to a log line. Doing it before the larger
changes is what makes them debuggable.

## Stage 2 — the two cheap security holes

**004** one shared store for both rate-limit counters · **006** a shorter token
lifetime

Hours of work each. They sit here rather than in Stage 0 because neither is
exploitable on a single instance behind a proxy — but both get quietly worse the
moment the deployment grows, which is exactly when nobody is looking at them.

## Stage 3 — the audit log

**005**

The highest-value missing piece, for the reasons its own file gives. It is also
what **010** needs before a room move can record what it did.

## Stage 4 — close the CSP hole properly

**003** move the Alpine components out of the templates, then **002** vendor the
three libraries and tighten the header

In that order: the header cannot lose `unsafe-inline` while the components live in
the HTML. 003 pays for itself anyway — the last three UI defects were all in code
no tool could see.

## Stage 5 — hygiene, then hardening

**007** replace `passlib` · **008** a lock file with hashes · **009** two-factor
authentication · **019** a load test of the front-desk flow

007 and 008 are worth folding into any change that touches dependencies. 019
needs a real deployment to measure, so it follows Stage 0.

## Stage 6 — what a hotel asks for next

**010** room move and stay extension · **011** rate plans · **012** cancellation
policy and deposits · **013** deliberate overbooking · **014** group bookings

In value order. Each file names the trigger that should start it, and two of them
first force the explicit-inventory decision recorded in `docs/LIMITATIONS.md`.

## Not in this sequence

- **Email notifications.** The one integration a guest actually notices, and an
  accepted absence today — `docs/LIMITATIONS.md`.
- **The test count in `README.md`** is stated twice and wrong both times; that
  and eighteen other consistency findings are in `docs/CLEANUP-BRIEF.md`, which
  is a one-session work order rather than part of this route.
