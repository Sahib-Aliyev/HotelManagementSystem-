# 018 — Error tracking and an uptime check

**Kind** operations · **Size** hours · **Depends on** 017

## What is wrong

Nothing reports that the application is broken except a person noticing. There is
no exception tracker and no external monitor, so a database outage at 03:00 is
discovered at the front desk in the morning.

## Fix

Sentry or equivalent for exceptions, and an external monitor on `/health`, which
already answers 503 when the database is unreachable rather than pretending to be
fine (`tests/test_security.py` pins that).

Do 017 first, so an exception in the tracker carries the request id that ties it
to the log line.

## Done when

Stopping the database container produces both a 503 from `/health` and an alert
that reaches somebody.
