---
paths:
  - "tests/**"
  - "pytest.ini"
  - ".github/workflows/**"
---

# Tests and CI

- Name a regression test after the state it pins, not after the fix:
  `test_a_room_cannot_hold_two_checked_in_stays` says what must stay true.
- The double-booking race test needs a real exclusion constraint, so it is
  PostgreSQL-only and skipped on SQLite; the invocation is under Commands in
  `CLAUDE.md`.
- CI gates: `ruff check`, `ruff format --check`, `pytest`, `alembic check` with a
  downgrade/upgrade round trip, a check that production will not start on unsafe
  settings, the PostgreSQL job for the exclusion constraint, and `pip-audit`
  (advisory).
- Verifying UI behaviour in the preview browser: it runs the page as a hidden
  tab, where CSS transitions never complete and programmatic scrolls fire no
  scroll events. Anything whose visibility depends on a transition cannot be
  measured there → `docs/history/review-2026-08-17.md`
