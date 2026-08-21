# 012 — Cancellation policy, deadlines and deposits

**Kind** feature · **Size** days · **Depends on** nothing

## What is wrong

Every cancellation is free. `cancel()` takes a reason and, for a stay that is
already checked in, a manager plus a recorded waiver — but it has no concept of a
fee, a deadline, or a forfeited deposit. A booking cancelled an hour before
arrival costs the hotel a night and the system charges nothing.

## Fix

A policy attached to the booking (free until N days before arrival, then a fee of
X or the first night), evaluated in `ReservationService.cancel()`, with the fee
becoming a real charge rather than a note. Deposits are the same model seen from
the other side: money already taken that is kept rather than refunded.

Two rules that already exist decide the shape of it:

- Money the hotel gives up is written down, with the manager who gave it up —
  `.claude/rules/money-and-billing.md`. A waived cancellation fee is exactly
  that, so it goes through the same recording path.
- A refund is a counter-entry, never an edit of the settled payment. Keeping part
  of a deposit is a partial refund, not a rewrite.

## Done when

Cancelling before the deadline is free, cancelling after it produces a charge on
the folio, waiving that charge needs a manager and is recorded, and a forfeited
deposit is visible as money kept rather than money that vanished.
