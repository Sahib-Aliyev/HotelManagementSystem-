# 014 — Group bookings

**Kind** feature · **Size** weeks · **Depends on** nothing

## What is wrong

One reservation is strictly one room. A tour group of twelve is twelve unrelated
reservations: twelve check-ins, twelve folios, twelve invoices, and no way to see
or bill them as one thing.

## Fix

A booking group that owns several reservations, with the operations that follow
from it: check the group in, settle one account for all of it, cancel it as a
unit. Each member stay stays a real reservation — the calendar, the availability
check and the exclusion constraint all keep working per room.

Note what this needs that does not exist yet: composing several service calls so
that they succeed or fail together. Today every service method commits on its
own, which is recorded under **Deliberately not done** in
`docs/LIMITATIONS.md`; a group check-in is the flow whose trigger fires that
entry.

## Done when

A group can be created, checked in and billed as one account, while each room's
stay is still an ordinary reservation on the calendar.
