# Open work

Every open item in this project, one file each, so that one can be picked up and
closed in a single sitting. This folder replaced `SECURITY-TODO.md` and
`BUGS-TODO.md` on **2026-08-21**: the same work was previously spread across two
long files plus `docs/ROADMAP.md` and `docs/LIMITATIONS.md`, four items were
filed in three or four places at once — two of them classified as "accepted" in
one file and "open" in another — and the five most consequential items (backups,
TLS, logging) appeared in no TODO file at all, only as prose in the roadmap.

- **This folder is the only place an open item is described.** `docs/ROADMAP.md`
  gives the order and names the numbers; `docs/LIMITATIONS.md` carries only what
  is *not* going to be done. Neither restates an item.
- **A file here means it is open.** Closing an item means deleting its file and
  recording it in `docs/history/fixed-bugs.md` — the contract is **Open work and
  history** in `CLAUDE.md`. The `/finding` skill walks the whole procedure.
- **Numbers are stable.** They are identifiers, not priorities; the order is
  below. A closed number is never reused.

The test that decides whether something belongs here rather than in
`docs/LIMITATIONS.md`: **does it have a fix and a *done when*?** If yes it is open
work, however far away it is. If there is no intention to do it, it is a
limitation.

## The items

| # | Item | Kind | Size | Depends on |
| --- | --- | --- | --- | --- |
| [001](001-pre-deploy-checklist.md) | Walk the pre-deployment checklist | configuration | hours | — |
| [002](002-csp-strict.md) | A strict CSP: drop `unsafe-inline` and `unsafe-eval` | security | days | 003 |
| [003](003-frontend-js-out-of-templates.md) | Move the Alpine components out of the templates | refactor | days | — |
| [004](004-redis-shared-counters.md) | One shared store for both rate-limit counters | security | hours | — |
| [005](005-audit-log.md) | An audit log for ordinary edits | feature | days | — |
| [006](006-token-lifetime.md) | Shorten the access-token lifetime | security | hours | — |
| [007](007-replace-passlib.md) | Replace `passlib` | dependency | hours | — |
| [008](008-dependency-lock-file.md) | A lock file with hashes | dependency | hours | — |
| [009](009-two-factor-auth.md) | Two-factor authentication for admin and manager | security | days | — |
| [010](010-room-move-and-stay-extension.md) | Room move and stay extension as real operations | feature | days | 005 |
| [011](011-rate-plans.md) | Rate plans instead of one number per booking | feature | weeks | — |
| [012](012-cancellation-policy.md) | Cancellation policy, deadlines and deposits | feature | days | — |
| [013](013-deliberate-overbooking.md) | Deliberate overbooking by policy | feature | days | 011 |
| [014](014-group-bookings.md) | Group bookings | feature | weeks | — |
| [015](015-backups-and-restore.md) | Backups and a tested restore | operations | hours | — |
| [016](016-tls-and-reverse-proxy.md) | TLS and a reverse proxy | operations | hours | — |
| [017](017-request-ids-and-structured-logs.md) | Request IDs and structured logs | operations | hours | — |
| [018](018-error-tracking-and-uptime.md) | Error tracking and an uptime check | operations | hours | 017 |
| [019](019-load-test-front-desk.md) | A load test of the front-desk flow | operations | hours | 016 |

## Order

Not by how interesting each one is, but by what would hurt most on the first real
night. `docs/ROADMAP.md` explains why the stages are in this order.

1. **Nothing may be deployed before these:** 015, 016, 001 — plus 004 and 006,
   which are hours of work each and are holes while they are open.
2. **Being able to see what happened:** 017, then 018.
3. **The CSP chain:** 003, then 002. 002 cannot finish first.
4. **The audit log:** 005 — the highest-value missing piece, and what 010 needs.
5. **Dependency hygiene:** 007 and 008, whenever a dependency is being touched
   anyway. Then 009, and 019 once there is a deployment to measure.
6. **Product work:** 010–014, each waiting on the trigger its own file names.

## Adding an item

Copy the shape of an existing file: what is wrong, where in the code, what was
reproduced or measured, the fix, and a *done when* that can be checked. A finding
with no measurement is a suspicion — reproduce it first, the way the entries in
`docs/history/` do.

Nothing here is a rule. Rules live in `CLAUDE.md` and `.claude/rules/`; an item
may point at one, never restate it.
