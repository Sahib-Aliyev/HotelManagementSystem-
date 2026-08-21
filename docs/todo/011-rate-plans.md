# 011 — Rate plans instead of one number per booking

**Kind** feature · **Size** weeks · **Depends on** nothing

## What is wrong

`nightly_rate` is a single number per booking, so seasonality means a manager
overriding the rate by hand on every reservation. That is most of why the
manager-only rate override exists at all — a workaround standing in for a
missing model.

## Fix

Per-night pricing, which is the point at which the derived-availability model
stops being enough: the explicit `room_nights` inventory table recorded under
**Deliberately not done** in `docs/LIMITATIONS.md` is the natural home for
per-night rates, and its trigger is exactly this item. Do that first rather than
building seasonal pricing twice.

All money arithmetic stays in one place whatever the model becomes — the rule is
in `.claude/rules/money-and-billing.md`, and a rate plan changes what feeds
`accommodation_charge()`, not where it lives.

## Done when

A stay spanning a rate change is priced per night, the folio shows the nights and
their rates, and the manager override is what it should be — an exception, not
the mechanism.
