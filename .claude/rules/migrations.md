---
paths:
  - "alembic/**"
  - "app/models/**"
---

# Migrations

- `alembic check` must pass; CI runs it together with a downgrade/upgrade
  round trip. Development builds its schema with `create_all()` and production
  migrates, so drift means the two have structurally different databases →
  `docs/history/audit-2026-08-19-architecture.md`
- A migration is fixed on **both** engines. On SQLite that means
  `batch_alter_table(copy_from=…, recreate="always")`, and the snapshot has to
  carry the table's indexes and constraints — a batch rebuild produces exactly
  what it is given → `docs/history/audit-2026-08-19-architecture.md`
- Batch mode recreates a table from reflection, and SQLite reflection returns
  no CHECK constraints, so a downgrade there drops the non-native enum checks.
  Acceptable on a rollback path, worth knowing before you rely on one.
- Adding a foreign-key column on SQLite: Alembic emits the constraint as a
  separate ALTER, which SQLite cannot do, and batch mode would lose the CHECK
  constraints. Write the `ALTER TABLE … ADD COLUMN … REFERENCES` by hand —
  see `alembic/versions/a1c4f7b920d3_*.py`.
