# Tests

One in-memory SQLite database per test, built by the fixtures in
`conftest.py`; `test_double_booking_pg.py` is the exception and needs
PostgreSQL.

- Conventions for this directory: `.claude/rules/tests.md`
- Every business rule needs a matching test — the rule is in `CLAUDE.md`.
- What each regression test is defending against: `docs/history/`
