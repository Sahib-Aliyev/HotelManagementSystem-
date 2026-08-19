"""Reporting correctness: every figure has to say which unit it is in.

Two findings of the 2026-08-19 audit live here, and they are the same mistake in
different clothing — a number printed without its basis.

`total_revenue` was cash received in the window while the room-type table
directly beneath it was accrued accommodation charges net of tax, so the screen
carried two revenues that could never be reconciled and neither was labelled.
`average_daily_rate` then divided one by the other's unit, reporting 354.00 for a
room sold at 150.00.

And a balance a manager had formally written off went on being counted as
receivable for ever, because `waived_amount` was recorded on the reservation and
never read by the dashboard.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import event

pytestmark = pytest.mark.asyncio

TODAY = date.today()
VAT = Decimal("0.18")


def iso(days_from_today: int) -> str:
    return (TODAY + timedelta(days=days_from_today)).isoformat()


async def _stay(client: AsyncClient, *, guest_id: int, room_id: int, nights: int = 2):
    created = await client.post(
        "/api/v1/reservations",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in_date": iso(0),
            "check_out_date": iso(nights),
            "adults": 1,
        },
    )
    assert created.status_code == 201, created.text
    reservation = created.json()
    checked_in = await client.post(f"/api/v1/reservations/{reservation['id']}/check-in")
    assert checked_in.status_code == 200
    return checked_in.json()


# ------------------------------------------------------------------ revenue
async def test_the_report_breakdown_adds_up_to_its_headline(manager_client, seeded):
    stay = await _stay(
        manager_client, guest_id=seeded["guests"][0].id, room_id=seeded["rooms"][1].id
    )
    folio = (await manager_client.get(f"/api/v1/payments/folio/{stay['id']}")).json()
    await manager_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": stay["id"],
            "amount": folio["total"],
            "method": "card",
        },
    )

    report = (await manager_client.get("/api/v1/reports/summary")).json()
    by_type = sum(Decimal(row["revenue"]) for row in report["room_type_performance"])
    assert Decimal(report["total_revenue"]) == by_type, (
        "the room-type table is the headline figure, broken down"
    )


async def test_revenue_and_cash_are_separate_and_named(manager_client, seeded):
    """A guest prepays two nights; the report window contains one of them.

    Cash is the whole prepayment, VAT included. Revenue is the one night earned,
    net of VAT. Both are right, and they are different numbers — which is why
    each has its own field.
    """
    stay = await _stay(
        manager_client, guest_id=seeded["guests"][0].id, room_id=seeded["rooms"][1].id
    )
    folio = (await manager_client.get(f"/api/v1/payments/folio/{stay['id']}")).json()
    await manager_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": stay["id"],
            "amount": folio["total"],
            "method": "card",
        },
    )

    report = (
        await manager_client.get(
            "/api/v1/reports/summary", params={"start": iso(0), "end": iso(0)}
        )
    ).json()

    nightly = Decimal(stay["nightly_rate"])
    assert report["total_nights"] == 1, "one night of the stay falls in the window"
    assert Decimal(report["total_revenue"]) == nightly
    assert Decimal(report["cash_collected"]) == Decimal(folio["total"])
    assert Decimal(report["cash_collected"]) > Decimal(report["total_revenue"])


async def test_adr_is_room_revenue_over_nights_sold(manager_client, seeded):
    """The figure owners benchmark. Prepayment must not look like a rate rise."""
    stay = await _stay(
        manager_client, guest_id=seeded["guests"][0].id, room_id=seeded["rooms"][1].id
    )
    folio = (await manager_client.get(f"/api/v1/payments/folio/{stay['id']}")).json()
    await manager_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": stay["id"],
            "amount": folio["total"],
            "method": "card",
        },
    )

    report = (
        await manager_client.get(
            "/api/v1/reports/summary", params={"start": iso(0), "end": iso(0)}
        )
    ).json()
    assert Decimal(report["average_daily_rate"]) == Decimal(stay["nightly_rate"]), (
        "ADR is the rate the room actually sold at, whatever was paid when"
    )


async def test_an_unpaid_stay_still_earns_revenue(manager_client, seeded):
    """Accrual, not cash: nights slept are earned whether or not anyone paid."""
    await _stay(
        manager_client, guest_id=seeded["guests"][0].id, room_id=seeded["rooms"][1].id
    )
    report = (
        await manager_client.get(
            "/api/v1/reports/summary", params={"start": iso(0), "end": iso(0)}
        )
    ).json()
    assert Decimal(report["total_revenue"]) > 0
    assert Decimal(report["cash_collected"]) == 0


# -------------------------------------------------------- outstanding balance
async def test_a_written_off_balance_stops_being_reported_as_owed(
    manager_client, seeded
):
    stay = await _stay(
        manager_client, guest_id=seeded["guests"][0].id, room_id=seeded["rooms"][1].id
    )
    before = (await manager_client.get("/api/v1/reports/dashboard")).json()["stats"]
    assert Decimal(before["outstanding_balance"]) > 0

    checked_out = await manager_client.post(
        f"/api/v1/reservations/{stay['id']}/check-out",
        json={"allow_outstanding_balance": True},
    )
    assert checked_out.status_code == 200
    waived = Decimal(checked_out.json()["waived_amount"])
    assert waived > 0, "the waiver is recorded on the reservation"

    after = (await manager_client.get("/api/v1/reports/dashboard")).json()["stats"]
    assert Decimal(after["outstanding_balance"]) == (
        Decimal(before["outstanding_balance"]) - waived
    ), "money the hotel decided to forgo is not money it is owed"


async def test_an_unpaid_stay_is_reported_owing_including_vat(manager_client, seeded):
    """The other half: a real debt still shows, and shows the VAT with it."""
    stay = await _stay(
        manager_client, guest_id=seeded["guests"][0].id, room_id=seeded["rooms"][1].id
    )
    stats = (await manager_client.get("/api/v1/reports/dashboard")).json()["stats"]
    expected = (Decimal(stay["total_price"]) * (1 + VAT)).quantize(Decimal("0.01"))
    assert Decimal(stats["outstanding_balance"]) == expected


async def test_one_overpaid_stay_cannot_mask_another_stays_debt(
    manager_client, seeded, db
):
    """The clamp is per reservation, not on the sum. Applied once at the end it
    let two errors hide each other and still look plausible."""
    from app.core.database import utcnow
    from app.models import Payment, PaymentMethod, PaymentStatus

    owing = await _stay(
        manager_client, guest_id=seeded["guests"][0].id, room_id=seeded["rooms"][1].id
    )
    credited = await _stay(
        manager_client, guest_id=seeded["guests"][1].id, room_id=seeded["rooms"][2].id
    )

    # Written straight to the table: the API caps a payment at what is owed, so
    # a credit balance can only arrive through data that predates that cap.
    db.add(
        Payment(
            reservation_id=credited["id"],
            amount=Decimal("5000.00"),
            method=PaymentMethod.CASH,
            status=PaymentStatus.PAID,
            paid_at=utcnow(),
        )
    )
    await db.commit()

    stats = (await manager_client.get("/api/v1/reports/dashboard")).json()["stats"]
    owed_on_first = (Decimal(owing["total_price"]) * (1 + VAT)).quantize(Decimal("0.01"))
    assert Decimal(stats["outstanding_balance"]) == owed_on_first, (
        "the credit on one stay must not net off the debt on another"
    )


# ------------------------------------------------------------- query volume
async def test_the_trends_do_not_query_once_per_day(manager_client, seeded, engine):
    """`occupied_on()` was called in a loop: 92 statements for a 90-day chart,
    and close to 370 at the report's 366-day cap."""
    counter = {"n": 0}

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    try:
        await _stay(
            manager_client,
            guest_id=seeded["guests"][0].id,
            room_id=seeded["rooms"][1].id,
        )

        counter["n"] = 0
        short = await manager_client.get("/api/v1/reports/occupancy-trend?days=14")
        for_14_days = counter["n"]

        counter["n"] = 0
        long = await manager_client.get("/api/v1/reports/occupancy-trend?days=90")
        for_90_days = counter["n"]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    assert short.status_code == 200 and long.status_code == 200
    assert len(long.json()) == 90, "still one point per day"
    assert for_90_days == for_14_days, (
        f"the query count follows the window: {for_14_days} vs {for_90_days}"
    )
    assert for_90_days < 10, f"{for_90_days} statements for one chart"


async def test_the_management_report_query_count_is_flat(
    manager_client, seeded, engine
):
    counter = {"n": 0}

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    try:
        await _stay(
            manager_client,
            guest_id=seeded["guests"][0].id,
            room_id=seeded["rooms"][1].id,
        )
        counter["n"] = 0
        await manager_client.get(
            "/api/v1/reports/summary", params={"start": iso(-300), "end": iso(0)}
        )
        for_300_days = counter["n"]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    assert for_300_days < 15, f"{for_300_days} statements for a 300-day report"


async def test_occupancy_counts_a_room_once_per_night(manager_client, seeded):
    """Expanding nights in Python has to reproduce COUNT(DISTINCT room_id):
    two consecutive stays in one room are one occupied room on each night."""
    room_id = seeded["rooms"][1].id
    first = await manager_client.post(
        "/api/v1/reservations",
        json={
            "guest_id": seeded["guests"][0].id,
            "room_id": room_id,
            "check_in_date": iso(0),
            "check_out_date": iso(1),
            "adults": 1,
        },
    )
    second = await manager_client.post(
        "/api/v1/reservations",
        json={
            "guest_id": seeded["guests"][1].id,
            "room_id": room_id,
            "check_in_date": iso(1),
            "check_out_date": iso(2),
            "adults": 1,
        },
    )
    assert first.status_code == 201 and second.status_code == 201

    trend = (await manager_client.get("/api/v1/reports/occupancy-trend?days=3")).json()
    today = next(p for p in trend if p["day"] == iso(0))
    assert today["occupied"] == 1, "one room is one room"
