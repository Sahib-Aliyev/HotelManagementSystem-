# 015 — Backups and a tested restore

**Kind** operations · **Size** hours · **Depends on** nothing

## What is wrong

PostgreSQL lives in a named Docker volume with no dump schedule and no restore
procedure. A hotel losing its folio history is an incident, not a bug — and an
untested restore is not a backup.

This was previously tracked in no TODO file at all, only as a stage in
`docs/ROADMAP.md`, which is how the most consequential item on the list stayed
the least specified.

## Fix

Nightly `pg_dump` to off-host storage, 7 daily plus 4 weekly, and the restore
drill written down in `docs/runbook.md` (which does not exist yet — create it
with this item).

## Done when

A restore into a scratch database reproduces the reservation and payment counts
of the source, and the drill has actually been run once by a person following the
written procedure.
