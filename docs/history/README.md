# How this system got here

Three reviews and their follow-ups, in the order they happened. Nothing here
is a rule to follow — the rules are in `CLAUDE.md` and `.claude/rules/`. This
is the record of what broke, how it was reproduced, and what was rejected on
the way, which is the part a diff cannot tell you.

| File | What it covers |
| --- | --- |
| `fixed-bugs.md` | The first six defects, found by using the app |
| `audit-2026-08-security.md` | First security audit: eleven gaps, all closed |
| `review-2026-08-17.md` | Second review: eleven findings, the two functional bugs, and the follow-ups |
| `audit-2026-08-19-architecture.md` | Architecture and production-readiness audit: eighteen findings, and the lesson about asking what *states* the app can reach |

Read it when you are about to change money, booking or room-status code, or
when a rule in `.claude/rules/` looks arbitrary and you want to know what it
cost to learn. `git log` is the other half of the same record.
