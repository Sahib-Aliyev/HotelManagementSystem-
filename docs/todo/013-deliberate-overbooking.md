# 013 — Deliberate overbooking by policy

**Kind** feature · **Size** days · **Depends on** 011

## What is wrong

Overbooking is impossible by construction: the service check refuses an overlap
and, on PostgreSQL, the `no_double_booking` exclusion constraint refuses it
again. Real hotels oversell by a policy percentage because no-shows are
predictable, and `NO_SHOW` is already tracked here — the data needed to set the
policy is being collected and cannot be acted on.

## Fix

An explicit, auditable exception rather than a hole. The constraint stays; what
changes is that a room can be sold beyond its inventory *up to a stated policy*,
recorded as such, so the front desk knows a walk-in may have to be rehoused
rather than discovering it at check-in.

This is deliberately sequenced **after** the exclusion constraint (already in
place) and after 011, because the explicit inventory table that rate plans force
is where an allotment or an overbooking allowance naturally lives — see
**Deliberately not done** in `docs/LIMITATIONS.md`.

Whatever the policy is, the two invariants that live in the database as well as
in Python stay as they are: the reasoning is in CLAUDE.md's **Architecture
rule**, and a deliberate exception must be expressible without weakening the
constraint for everything else.

## Done when

A property can be oversold by its configured percentage, every oversell is
visible as one, and an accidental double booking is still refused with a 409.
