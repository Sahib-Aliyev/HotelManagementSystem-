# Migrations

Alembic owns the schema in production; development builds it with
`create_all()`, which is why `alembic check` is a CI gate rather than a
suggestion.

- Conventions for this directory: `.claude/rules/migrations.md`
- The SQLite/PostgreSQL differences that shaped these revisions:
  `docs/history/audit-2026-08-19-architecture.md`
