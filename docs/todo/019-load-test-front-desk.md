# 019 — A load test of the front-desk flow

**Kind** operations · **Size** hours · **Depends on** 016

## What is wrong

Two performance fixes are documented as improvements with no numbers attached:
moving bcrypt and ReportLab off the event loop
(`.claude/rules/services-runtime.md`) and the N+1 work in the reservation
queries. Both are described as "it stalled the whole process" and "it was slow",
which is a claim, not a measurement.

## Fix

A load test of the real front-desk flow — sign in, search, check in, take
payment, check out — run against a deployment behind the Stage 0 proxy, with the
numbers recorded in `docs/history/` the way the audit figures are.

Run `tests/test_double_booking_pg.py` against that same deployment with two
workers while it is set up: the exclusion constraint is what makes concurrency
safe, and it is worth proving in situ rather than trusting the single-process
case.

## Done when

The two fixes have measured before/after figures written down, and the
double-booking test passes against a multi-worker deployment.
