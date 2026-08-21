---
paths:
  - "app/services/pricing.py"
  - "app/services/payment_service.py"
  - "app/services/invoice_service.py"
  - "app/services/report_service.py"
  - "app/repositories/payment_repo.py"
  - "app/routers/api/payments.py"
  - "app/routers/api/reports.py"
  - "app/schemas/payment.py"
  - "app/schemas/report.py"
---

# Money and billing

Every figure a guest or a manager reads comes from here. Three of these rules
exist because the same class of bug was shipped more than once.

## Standing rules

- **All money arithmetic lives in `app/services/pricing.py`.**
  `accommodation_charge(rate, nights)`, `tax_on(subtotal)` and
  `total_due(reservation)` are the only definitions; nothing recomputes
  `rate × nights` or a tax share of its own. Three places used to, and the folio
  was deriving its subtotal one way while taking its total another, so the tax
  line silently absorbed the difference between them.
- **Never compare a payment against `Reservation.total_price` directly** —
  it is net of tax. What the guest actually owes is
  `app/services/pricing.py::total_due()`, which adds VAT. Using
  `total_price` alone lets a guest check out having paid the room charge but
  never the tax — see `docs/history/review-2026-08-17.md`. The dashboard
  aggregate in
  `ReportService._outstanding_balance` is the same rule in SQL form.
- **Payments are append-only.** A refund is a new `Payment` row with
  `refunded_payment_id` pointing at the settled row it reverses; the settled
  row is never edited. Anything that sums money therefore has to go through
  `is_cash_movement()` and `signed_amount()` in
  `app/repositories/payment_repo.py`, which count a counter-entry as negative.
  Filtering on `status == PAID` alone silently ignores every refund.
- **Money the hotel gives up is written down.** Both paths that forgive a
  balance — check-out with `allow_outstanding_balance`, and cancelling a stay
  that is already checked in — require a manager and record
  `waived_amount` / `waived_at` / `waived_by_id` on the reservation
  (`ReservationService._record_waiver`). A new way to forgive money must do
  the same.
- **A report figure has to name its basis.** `total_revenue` is accrual (nights
  consumed in the window, net of tax) and `cash_collected` is cash (payments
  received, VAT included). They are different numbers and both are correct.
  Never divide one by the other, and never put an unlabelled "revenue" on a
  screen beside a breakdown computed the other way. This went wrong twice:
  `docs/history/audit-2026-08-19-architecture.md` and
  `docs/history/review-2026-08-17.md`.

## Lifted from the audits

- Invoice numbers come from the `invoice_counters` table via
  `UPDATE … RETURNING`, never `COUNT(*) + 1`; a gap left by a rolled-back
  transaction is expected and harmless →
  `docs/history/audit-2026-08-19-architecture.md`
- `ReportService._outstanding_balance()` subtracts `COALESCE(waived_amount, 0)`
  and clamps **per reservation**, not on the final sum — clamping once at the
  end lets an overpaid stay net off another stay's debt →
  `docs/history/audit-2026-08-19-architecture.md`
- Per-day aggregation is one query with the nights expanded in Python, so no
  dialect-specific date truncation is needed (`occupied_per_day`,
  `revenue_by_day`) → `docs/history/audit-2026-08-19-architecture.md`
- `ReservationService._price()` refuses a total above the `Numeric(10, 2)`
  ceiling rather than letting SQLite store it silently and PostgreSQL fail
  mid-transaction → `docs/history/review-2026-08-17.md`
- Refunding the same payment twice is a 409; the counter-entry carries
  `REFUND-<reference>` so it cannot collide with the row it reverses →
  `docs/history/review-2026-08-17.md`
