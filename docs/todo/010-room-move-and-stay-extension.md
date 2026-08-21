# 010 — Room move and stay extension as real operations

**Kind** feature · **Size** days · **Depends on** 005

## What is wrong

These are the two most common front-desk actions after check-in, and neither
exists. Both are done today by `PATCH`-ing `room_id` or `check_out_date`, which:

- silently re-prices the stay at the new room type's base rate, and
- leaves no record that a move or an extension happened at all — only the new
  values, attributed to nobody.

A guest who moves rooms on night two and is charged the new rate for all five
nights has no way to see why, and neither does the receptionist.

## Fix

Two explicit operations in `ReservationService`, each with its own guard rails,
its own role check on the state change, and its own audit row (which is why 005
comes first). The pricing consequence has to be a decision the operation states,
not a side effect of a field assignment: which nights are charged at which rate.

Everything the generic `PATCH` already enforces still has to hold — the stay
range lives in one place and re-derives on every update; that is a **Security
rule** in `CLAUDE.md`.

## Done when

A move and an extension are each one request, each records what changed, and the
resulting folio shows the nights at the rates that were actually agreed.
