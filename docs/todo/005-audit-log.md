# 005 — An audit log for ordinary edits

**Kind** feature · **Size** days · **Depends on** nothing

The highest-value thing missing from this system, and previously the only item
filed in four places at once.

## What is wrong

Attribution exists exactly where money moves or is given up:
`Reservation.created_by_id` and `waived_by_id`, `Payment.recorded_by_id` (on the
payment and on the refund counter-entry). What does not exist is a before/after
trail for **ordinary edits** — who changed a price, a date or a room, and what it
was before. Those changes are attributed to nobody.

It is also the reason three findings of the 2026-08-19 audit were worse than they
had to be (cancelling a stay, refunding a payment, waiving a balance): there was
no way to see what a stay had looked like before someone changed it.

In a system that touches money, that log is the only argument available when
something is disputed.

## Fix

One table — `actor, action, object, before, after, at` — written from the service
layer, which is already the single choke point every write passes through. The
layer order and where a rule of this kind belongs are the **Architecture rule**
in `CLAUDE.md`.

Do not write it from the routers, and do not write it from the repositories: a
router does not know the business meaning of the change and a repository does not
know who made it.

## Done when

Changing a rate, a date and a room each leave one row, a stay can show who
changed what and when, and the reported figures do not move when the log is
written (it records, it does not participate).
