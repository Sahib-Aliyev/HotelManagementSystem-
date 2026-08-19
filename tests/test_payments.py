"""Money correctness: VAT is part of what is owed, not an optional extra.

Regression coverage for a bug where `balance_due` and the payment
"outstanding" check were computed against `Reservation.total_price`, which is
net of tax. A guest who paid only the pre-tax accommodation charge showed a
balance of 0.00 and could check out with the VAT never collected.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

TODAY = date.today()


def iso(days_from_today: int) -> str:
    return (TODAY + timedelta(days=days_from_today)).isoformat()


async def _book_and_check_in(client: AsyncClient, *, guest_id: int, room_id: int) -> dict:
    created = await client.post(
        "/api/v1/reservations",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in_date": iso(0),
            "check_out_date": iso(3),  # 3 nights
            "adults": 1,
        },
    )
    assert created.status_code == 201
    reservation = created.json()

    checked_in = await client.post(f"/api/v1/reservations/{reservation['id']}/check-in")
    assert checked_in.status_code == 200
    return checked_in.json()


async def test_balance_due_includes_vat_not_just_the_room_charge(
    reception_client, seeded
):
    reservation = await _book_and_check_in(
        reception_client,
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id,  # Double, 150.00/night, 3 nights = 450.00
    )
    subtotal = Decimal(reservation["total_price"])
    assert subtotal == Decimal("450.00")

    await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation["id"],
            "amount": str(subtotal),
            "method": "cash",
        },
    )

    folio = await reception_client.get(f"/api/v1/payments/folio/{reservation['id']}")
    body = folio.json()
    expected_tax = (subtotal * Decimal("0.18")).quantize(Decimal("0.01"))

    assert Decimal(body["amount_paid"]) == subtotal
    assert Decimal(body["balance_due"]) == expected_tax, (
        "balance_due must be the unpaid VAT, not zero — paying the room "
        "charge alone does not settle the tax"
    )


async def test_checkout_is_blocked_until_vat_is_paid(reception_client, seeded):
    reservation = await _book_and_check_in(
        reception_client,
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id,
    )
    subtotal = Decimal(reservation["total_price"])

    await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation["id"],
            "amount": str(subtotal),
            "method": "cash",
        },
    )

    blocked = await reception_client.post(
        f"/api/v1/reservations/{reservation['id']}/check-out"
    )
    assert blocked.status_code == 409, (
        "check-out must not succeed while VAT is still outstanding"
    )

    tax = (subtotal * Decimal("0.18")).quantize(Decimal("0.01"))
    paid_tax = await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation["id"],
            "amount": str(tax),
            "method": "cash",
        },
    )
    assert paid_tax.status_code == 201, (
        "a payment for exactly the outstanding VAT must be accepted"
    )

    allowed = await reception_client.post(
        f"/api/v1/reservations/{reservation['id']}/check-out"
    )
    assert allowed.status_code == 200


async def test_a_payment_for_more_than_the_vat_inclusive_total_is_rejected(
    reception_client, seeded
):
    reservation = await _book_and_check_in(
        reception_client,
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id,
    )
    total_with_vat = Decimal(reservation["total_price"]) * Decimal("1.18")

    overpaid = await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation["id"],
            "amount": str(total_with_vat + Decimal("1.00")),
            "method": "cash",
        },
    )
    assert overpaid.status_code == 422


async def test_the_dashboard_reports_the_vat_inclusive_amount_owed(
    reception_client, seeded
):
    """The dashboard aggregate was the fourth site computing money owed from
    `total_price`, which is net of tax — so it disagreed with the folio of
    every reservation by exactly the VAT share."""
    reservation = await _book_and_check_in(
        reception_client,
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id,  # 150.00 x 3 nights = 450.00
    )
    expected = Decimal("450.00") * Decimal("1.18")

    reservation_view = await reception_client.get(
        f"/api/v1/reservations/{reservation['id']}"
    )
    assert Decimal(reservation_view.json()["balance_due"]) == expected

    dashboard = await reception_client.get("/api/v1/reports/dashboard")
    assert Decimal(dashboard.json()["stats"]["outstanding_balance"]) == expected


async def test_a_refund_is_a_counter_entry_and_leaves_the_original_intact(
    reception_client, seeded
):
    """Refunding used to overwrite the settled payment: its status, its note,
    and every trace that money had ever been received. A manager could pocket
    cash and leave the guest showing as unpaid."""
    reservation = await _book_and_check_in(
        reception_client,
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id,
    )
    reservation_id = reservation["id"]

    taken = await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation_id,
            "amount": "100.00",
            "method": "cash",
            "note": "cash taken at desk",
        },
    )
    assert taken.status_code == 201
    payment_id = taken.json()["id"]

    await reception_client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.az", "password": "Manager1234"},
    )
    refunded = await reception_client.post(
        f"/api/v1/payments/{payment_id}/refund", params={"note": "erased"}
    )
    assert refunded.status_code == 201 or refunded.status_code == 200
    counter_entry = refunded.json()
    assert counter_entry["id"] != payment_id
    assert counter_entry["refunded_payment_id"] == payment_id
    assert counter_entry["status"] == "refunded"

    rows = await reception_client.get(f"/api/v1/payments/reservation/{reservation_id}")
    original = next(r for r in rows.json() if r["id"] == payment_id)
    assert original["status"] == "paid", "the settled payment must not be edited"
    assert original["note"] == "cash taken at desk"
    assert Decimal(original["amount"]) == Decimal("100.00")

    # The refund still has to reduce what the guest has paid.
    folio = await reception_client.get(f"/api/v1/payments/folio/{reservation_id}")
    assert Decimal(folio.json()["amount_paid"]) == Decimal("0.00")

    again = await reception_client.post(f"/api/v1/payments/{payment_id}/refund")
    assert again.status_code == 409, "one payment cannot be refunded twice"


async def test_a_pending_payment_cannot_exceed_the_balance_either(
    reception_client, seeded
):
    """The overpayment ceiling was gated on `status == paid`, and `status` is
    client-settable — so any amount went through as "pending"."""
    reservation = await _book_and_check_in(
        reception_client,
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id,
    )

    absurd = await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation["id"],
            "amount": "99999999.99",
            "method": "cash",
            "status": "pending",
        },
    )
    assert absurd.status_code == 422
