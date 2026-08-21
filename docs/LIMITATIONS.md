# Known limitations

Open work lives in two separate files: **`SECURITY-TODO.md`** (security findings
and the pre-deployment checklist) and **`BUGS-TODO.md`** (functional defects that
are not security issues). What follows is limitations that are deliberately
accepted.

- No email notifications, and only a single currency (`CURRENCY` in `.env`).
- The CSP still allows `unsafe-inline` and `unsafe-eval`, because Tailwind,
  Alpine and Chart.js load from CDNs and Tailwind compiles styles in the
  browser. Vendoring those three files is what allows a strict CSP.
- Rate limiting is per-IP with a per-account lockout on top
  (`ACCOUNT_LOCK_AFTER_FAILURES`), and defaults to in-memory storage: behind a
  proxy the real client IP must be forwarded, and more than one instance needs
  `RATE_LIMIT_STORAGE_URI` pointed at Redis. The per-account counter is
  in-process too, with the same caveat — it is bounded and expiring now, so it
  cannot grow without limit, but two instances still keep separate counts.
- **The no-double-booking constraint is PostgreSQL-only.** SQLite cannot express
  an exclusion constraint, so on SQLite the application-level check in
  `_assert_room_free` stands alone and a genuine write race is theoretically
  open — SQLite serialises writers, which mitigates it in practice. Treat
  PostgreSQL as the supported deployment target for anything real.
- No audit log, and it is the highest-value thing missing. Who took a payment
  (`recorded_by_id`), who refunded it (the
  counter-entry's `recorded_by_id`), who created a reservation
  (`created_by_id`) and who waived a balance (`waived_by_id`) are recorded, but
  there is no before/after trail for ordinary edits — a price change or a date
  change is not attributed to anyone.
- No two-factor authentication.
