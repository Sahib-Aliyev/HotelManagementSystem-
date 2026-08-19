"""Booking rules — above all, that a room is never sold twice for one night."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models import Reservation, ReservationStatus
from app.repositories.reservation_repo import ReservationRepository

pytestmark = pytest.mark.asyncio

TODAY = date.today()


def iso(days_from_today: int) -> str:
    return (TODAY + timedelta(days=days_from_today)).isoformat()


async def book(
    client: AsyncClient,
    *,
    guest_id: int,
    room_id: int,
    check_in: int,
    check_out: int,
    adults: int = 1,
    children: int = 0,
):
    return await client.post(
        "/api/v1/reservations",
        json={
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in_date": iso(check_in),
            "check_out_date": iso(check_out),
            "adults": adults,
            "children": children,
        },
    )


# --------------------------------------------------------------- happy path
async def test_booking_is_created_and_priced(reception_client, seeded):
    response = await book(
        reception_client,
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id,  # Double, 150.00/night
        check_in=1,
        check_out=4,
    )
    assert response.status_code == 201

    body = response.json()
    assert body["nights"] == 3
    assert float(body["nightly_rate"]) == 150.00
    assert float(body["total_price"]) == 450.00
    assert body["status"] == "confirmed"
    assert body["reference"].startswith("BK")


async def test_each_booking_gets_a_unique_reference(reception_client, seeded):
    first = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][0].id, check_in=1, check_out=2,
    )
    second = await book(
        reception_client, guest_id=seeded["guests"][1].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=2,
    )
    assert first.json()["reference"] != second.json()["reference"]


# ------------------------------------------------------------------ walk-in
async def test_walk_in_registers_guest_and_books_in_one_call(reception_client, seeded):
    response = await reception_client.post(
        "/api/v1/reservations/walk-in",
        json={
            "room_id": seeded["rooms"][1].id,  # Double, 150.00/night
            "check_in_date": iso(0),
            "check_out_date": iso(2),
            "guest": {
                "full_name": "Walk-in Wendy",
                "phone": "+994551112233",
                "document_type": "passport",
                "document_number": "WALKIN1",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert float(body["nightly_rate"]) == 150.00
    assert body["guest"]["full_name"] == "Walk-in Wendy"


async def test_walk_in_honours_a_nightly_rate_override(manager_client, seeded):
    """Regression test: the override used to be silently dropped for new guests.

    Driven by a manager because overriding the rate is now a manager-only
    action; the receptionist half of that rule lives in test_security.py.
    """
    response = await manager_client.post(
        "/api/v1/reservations/walk-in",
        json={
            "room_id": seeded["rooms"][1].id,  # base rate 150.00/night
            "check_in_date": iso(0),
            "check_out_date": iso(2),
            "nightly_rate": "99.00",
            "guest": {
                "full_name": "Discount Dan",
                "phone": "+994551112244",
                "document_type": "passport",
                "document_number": "WALKIN2",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert float(body["nightly_rate"]) == 99.00
    assert float(body["total_price"]) == 198.00


# ------------------------------------------------- overbooking prevention
async def test_identical_dates_are_rejected(reception_client, seeded):
    room_id = seeded["rooms"][1].id
    first = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=room_id, check_in=5, check_out=8,
    )
    assert first.status_code == 201

    clash = await book(
        reception_client, guest_id=seeded["guests"][1].id,
        room_id=room_id, check_in=5, check_out=8,
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    ("check_in", "check_out", "description"),
    [
        (6, 7, "entirely inside the existing stay"),
        (4, 6, "starts before, ends inside"),
        (7, 10, "starts inside, ends after"),
        (3, 12, "completely surrounds the existing stay"),
    ],
)
async def test_partial_overlaps_are_rejected(
    reception_client, seeded, check_in, check_out, description
):
    room_id = seeded["rooms"][1].id
    existing = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=room_id, check_in=5, check_out=9,
    )
    assert existing.status_code == 201

    clash = await book(
        reception_client, guest_id=seeded["guests"][1].id,
        room_id=room_id, check_in=check_in, check_out=check_out,
    )
    assert clash.status_code == 409, f"should reject a stay {description}"


async def test_same_day_turnover_is_allowed(reception_client, seeded):
    """One guest checks out the morning another checks in — not an overlap."""
    room_id = seeded["rooms"][1].id
    await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=room_id, check_in=2, check_out=5,
    )
    turnover = await book(
        reception_client, guest_id=seeded["guests"][1].id,
        room_id=room_id, check_in=5, check_out=7,
    )
    assert turnover.status_code == 201


async def test_cancelling_frees_the_room(reception_client, seeded):
    room_id = seeded["rooms"][1].id
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=room_id, check_in=3, check_out=6,
    )
    reservation_id = booking.json()["id"]

    blocked = await book(
        reception_client, guest_id=seeded["guests"][1].id,
        room_id=room_id, check_in=3, check_out=6,
    )
    assert blocked.status_code == 409

    await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/cancel", json={"reason": "Test"}
    )

    now_free = await book(
        reception_client, guest_id=seeded["guests"][1].id,
        room_id=room_id, check_in=3, check_out=6,
    )
    assert now_free.status_code == 201


# ------------------------------------------------------------- validation
async def test_past_check_in_is_rejected(reception_client, seeded):
    response = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][0].id, check_in=-3, check_out=2,
    )
    assert response.status_code == 422


async def test_check_out_must_follow_check_in(reception_client, seeded):
    response = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][0].id, check_in=5, check_out=5,
    )
    assert response.status_code == 422


async def test_occupancy_cannot_exceed_room_capacity(reception_client, seeded):
    response = await book(
        reception_client,
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][0].id,  # Single, sleeps 1
        check_in=1,
        check_out=2,
        adults=2,
    )
    assert response.status_code == 422


async def test_booking_an_unknown_room_is_a_404(reception_client, seeded):
    response = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=99999, check_in=1, check_out=2,
    )
    assert response.status_code == 404


# ---------------------------------------------------------- availability
async def test_availability_excludes_a_booked_room(reception_client, seeded):
    room_id = seeded["rooms"][1].id
    await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=room_id, check_in=4, check_out=7,
    )

    response = await reception_client.get(
        "/api/v1/rooms/availability",
        params={"check_in_date": iso(4), "check_out_date": iso(7)},
    )
    assert response.status_code == 200
    assert room_id not in [room["id"] for room in response.json()]


async def test_availability_filters_by_capacity(reception_client, seeded):
    response = await reception_client.get(
        "/api/v1/rooms/availability",
        params={"check_in_date": iso(1), "check_out_date": iso(2), "capacity": 2},
    )
    rooms = response.json()
    assert rooms
    assert all(room["room_type"]["capacity"] >= 2 for room in rooms)


async def test_maintenance_rooms_are_never_offered(reception_client, seeded):
    room_id = seeded["rooms"][2].id
    await reception_client.post(
        f"/api/v1/rooms/{room_id}/status", params={"new_status": "maintenance"}
    )

    response = await reception_client.get(
        "/api/v1/rooms/availability",
        params={"check_in_date": iso(1), "check_out_date": iso(3)},
    )
    assert room_id not in [room["id"] for room in response.json()]

    blocked = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=room_id, check_in=1, check_out=3,
    )
    assert blocked.status_code == 409


# ------------------------------------------------------------- lifecycle
async def test_cannot_check_in_before_the_arrival_date(reception_client, seeded):
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][0].id, check_in=5, check_out=7,
    )
    response = await reception_client.post(
        f"/api/v1/reservations/{booking.json()['id']}/check-in"
    )
    assert response.status_code == 409


async def test_full_stay_lifecycle(reception_client, seeded):
    room_id = seeded["rooms"][1].id
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=room_id, check_in=0, check_out=2,
    )
    reservation_id = booking.json()["id"]

    checked_in = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-in"
    )
    assert checked_in.status_code == 200
    assert checked_in.json()["status"] == "checked_in"
    assert checked_in.json()["actual_check_in"] is not None

    room = await reception_client.get(f"/api/v1/rooms/{room_id}")
    assert room.json()["status"] == "occupied"

    # Money is owed, so check-out is refused.
    refused = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-out"
    )
    assert refused.status_code == 409

    # Paying the room charge alone would leave VAT outstanding — pay the
    # folio's VAT-inclusive total instead.
    folio = (await reception_client.get(f"/api/v1/payments/folio/{reservation_id}")).json()
    await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation_id,
            "amount": folio["total"],
            "method": "card",
            "status": "paid",
        },
    )

    checked_out = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-out"
    )
    assert checked_out.status_code == 200
    assert checked_out.json()["status"] == "checked_out"

    room = await reception_client.get(f"/api/v1/rooms/{room_id}")
    assert room.json()["status"] == "cleaning"


async def test_double_check_in_is_rejected(reception_client, seeded):
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=0, check_out=2,
    )
    reservation_id = booking.json()["id"]

    assert (await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-in")).status_code == 200
    assert (await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-in")).status_code == 409


async def test_completed_stay_cannot_be_cancelled(reception_client, seeded):
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=0, check_out=2,
    )
    reservation_id = booking.json()["id"]

    await reception_client.post(f"/api/v1/reservations/{reservation_id}/check-in")
    # Settled in full rather than waived: waiving a balance is a manager
    # action now, and this test is about cancelling a completed stay.
    folio = await reception_client.get(f"/api/v1/payments/folio/{reservation_id}")
    await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation_id,
            "amount": folio.json()["balance_due"],
            "method": "cash",
        },
    )
    checked_out = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-out"
    )
    assert checked_out.status_code == 200

    response = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/cancel", json={"reason": "Too late"}
    )
    assert response.status_code == 409


# --------------------------------------------------------------- payments
async def test_overpayment_is_rejected(reception_client, seeded):
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    response = await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": booking.json()["id"],
            "amount": float(booking.json()["total_price"]) + 100,
            "method": "cash",
            "status": "paid",
        },
    )
    assert response.status_code == 422


async def test_folio_applies_vat_and_tracks_the_balance(reception_client, seeded):
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    reservation_id = booking.json()["id"]

    folio = (await reception_client.get(f"/api/v1/payments/folio/{reservation_id}")).json()
    assert float(folio["subtotal"]) == 300.00
    assert float(folio["tax_amount"]) == 54.00  # 18% VAT
    assert float(folio["total"]) == 354.00
    # Nothing paid yet, so the whole VAT-inclusive total is owed — not just
    # the room charge.
    assert float(folio["balance_due"]) == 354.00

    await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation_id,
            "amount": 150.00,
            "method": "cash",
            "status": "paid",
        },
    )
    folio = (await reception_client.get(f"/api/v1/payments/folio/{reservation_id}")).json()
    assert float(folio["amount_paid"]) == 150.00
    assert float(folio["balance_due"]) == 204.00  # 354.00 - 150.00, VAT included


async def test_invoice_pdf_is_generated(reception_client, seeded):
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    reservation_id = booking.json()["id"]
    issued = await reception_client.post(
        f"/api/v1/invoices/reservation/{reservation_id}"
    )
    assert issued.status_code == 201

    response = await reception_client.get(
        f"/api/v1/invoices/reservation/{reservation_id}/pdf"
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


async def test_the_pdf_route_does_not_issue_an_invoice_by_itself(
    reception_client, seeded
):
    """A GET must not write to the database.

    `render_pdf` used to call `issue()`, so fetching the PDF created the
    invoice row and consumed a number from the sequence — and with a
    samesite=lax cookie, a link in an email was enough to trigger it.
    """
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    reservation_id = booking.json()["id"]

    pdf = await reception_client.get(
        f"/api/v1/invoices/reservation/{reservation_id}/pdf"
    )
    assert pdf.status_code == 404

    still_none = await reception_client.get(
        f"/api/v1/invoices/reservation/{reservation_id}"
    )
    assert still_none.status_code == 404, "the GET must not have created anything"


async def test_issuing_an_invoice_twice_returns_the_same_one(reception_client, seeded):
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    reservation_id = booking.json()["id"]
    path = f"/api/v1/invoices/reservation/{reservation_id}"

    first = await reception_client.post(path)
    second = await reception_client.post(path)
    assert first.json()["invoice_number"] == second.json()["invoice_number"]


# ----------------------------------------------------------------- guests
async def test_duplicate_document_number_is_rejected(reception_client):
    payload = {
        "full_name": "First Person",
        "phone": "+994551234567",
        "document_type": "passport",
        "document_number": "DUP12345",
    }
    assert (await reception_client.post("/api/v1/guests", json=payload)).status_code == 201

    payload["full_name"] = "Second Person"
    clash = await reception_client.post("/api/v1/guests", json=payload)
    assert clash.status_code == 409
    assert "guest_id" in clash.json()["error"]["details"]


async def test_document_number_is_normalised(reception_client):
    response = await reception_client.post(
        "/api/v1/guests",
        json={
            "full_name": "Spacey Document",
            "phone": "+994551112233",
            "document_type": "passport",
            "document_number": "ab 12 34 cd",
        },
    )
    assert response.json()["document_number"] == "AB1234CD"


async def test_guest_search_matches_phone_and_document(reception_client, seeded):
    by_name = await reception_client.get("/api/v1/guests", params={"q": "alice"})
    assert by_name.json()["total"] == 1

    by_document = await reception_client.get("/api/v1/guests", params={"q": "P1000002"})
    assert by_document.json()["items"][0]["full_name"] == "Bob Tester"


async def test_future_date_of_birth_is_rejected(reception_client):
    response = await reception_client.post(
        "/api/v1/guests",
        json={
            "full_name": "Time Traveller",
            "phone": "+994559998877",
            "document_type": "passport",
            "document_number": "FUTURE1",
            "date_of_birth": iso(365),
        },
    )
    assert response.status_code == 422


# ------------------------------------------------------------- front desk
async def test_front_desk_lists_todays_arrivals(reception_client, seeded):
    await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=0, check_out=2,
    )
    board = (await reception_client.get("/api/v1/reservations/front-desk")).json()
    assert len(board["arrivals"]) == 1
    assert board["arrivals"][0]["guest"]["full_name"] == "Alice Tester"


async def test_dashboard_reports_occupancy(reception_client, seeded):
    await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=0, check_out=3,
    )
    stats = (await reception_client.get("/api/v1/reports/dashboard")).json()["stats"]
    assert stats["rooms_total"] == 3
    assert stats["rooms_occupied"] == 1
    assert stats["occupancy_rate"] == pytest.approx(33.3, abs=0.1)


# ------------------------------------------------------------ PATCH date rules
async def test_patch_cannot_stretch_a_stay_past_the_maximum(reception_client, seeded):
    """`create` caps a stay at 365 nights; PATCH used to cap nothing.

    A single request took the room off sale until the year 9999 and re-priced
    the stay at 291,221,300.00 — over what Numeric(10, 2) can hold.
    """
    booking_response = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    reservation_id = booking_response.json()["id"]

    stretched = await reception_client.patch(
        f"/api/v1/reservations/{reservation_id}",
        json={"check_out_date": "9999-12-31"},
    )
    assert stretched.status_code == 422

    unchanged = await reception_client.get(f"/api/v1/reservations/{reservation_id}")
    assert unchanged.json()["nights"] == 2


async def test_patch_cannot_backdate_a_stay(reception_client, seeded):
    """Backdating feeds fabricated nights into occupancy and ADR."""
    booking_response = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    reservation_id = booking_response.json()["id"]

    backdated = await reception_client.patch(
        f"/api/v1/reservations/{reservation_id}",
        json={"check_in_date": iso(-30), "check_out_date": iso(-20)},
    )
    assert backdated.status_code == 422


async def test_patch_still_accepts_a_legitimate_change(reception_client, seeded):
    """The guard above must not block ordinary edits."""
    booking_response = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    reservation_id = booking_response.json()["id"]

    extended = await reception_client.patch(
        f"/api/v1/reservations/{reservation_id}", json={"check_out_date": iso(5)}
    )
    assert extended.status_code == 200
    assert extended.json()["nights"] == 4
    assert float(extended.json()["total_price"]) == 600.00


@pytest.mark.parametrize("field", ["check_in_date", "adults", "nightly_rate"])
async def test_patch_with_an_explicit_null_is_rejected_not_a_crash(
    reception_client, seeded, field
):
    """An explicit JSON null survives `exclude_unset`.

    `data.get(field, <current>)` then returned None instead of the stored
    value, and the arithmetic below it raised a TypeError — an unhandled 500.
    """
    booking_response = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    reservation_id = booking_response.json()["id"]

    response = await reception_client.patch(
        f"/api/v1/reservations/{reservation_id}", json={field: None}
    )
    assert response.status_code == 200, "a null on an optional field is a no-op"

    unchanged = await reception_client.get(f"/api/v1/reservations/{reservation_id}")
    assert unchanged.json()["nights"] == 2
    assert unchanged.json()["adults"] == 1


async def test_walk_in_with_an_inverted_date_range_is_a_422(reception_client, seeded):
    """QuickBookingCreate had no range validator of its own, so the router
    built a ReservationCreate that raised inside the handler as a 500."""
    response = await reception_client.post(
        "/api/v1/reservations/walk-in",
        json={
            "room_id": seeded["rooms"][1].id,
            "check_in_date": iso(3),
            "check_out_date": iso(1),
            "guest": {
                "full_name": "Backwards Bob",
                "phone": "+994500000999",
                "document_number": "P9000999",
            },
        },
    )
    assert response.status_code == 422


# ------------------------------------------------- overdue and stale bookings
async def test_front_desk_shows_a_departure_that_is_already_overdue(
    reception_client, db, seeded
):
    """An exact `check_out_date == today` match hid overdue guests entirely.

    They stayed `checked_in` with a check-out date in the past, so they matched
    no day, appeared in no Departures column, and counted as zero on the
    dashboard — while physically still holding the room.
    """
    overdue = Reservation(
        reference="BK26-OVERDU",
        guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][0].id,
        check_in_date=TODAY - timedelta(days=6),
        check_out_date=TODAY - timedelta(days=4),
        status=ReservationStatus.CHECKED_IN,
        nightly_rate=Decimal("100.00"),
        total_price=Decimal("200.00"),
    )
    db.add(overdue)
    await db.commit()

    board = await reception_client.get("/api/v1/reservations/front-desk")
    references = [r["reference"] for r in board.json()["departures"]]
    assert "BK26-OVERDU" in references

    dashboard = await reception_client.get("/api/v1/reports/dashboard")
    assert dashboard.json()["stats"]["departures_today"] >= 1


async def test_front_desk_shows_an_arrival_whose_date_has_passed(
    reception_client, db, seeded
):
    """A booking that never arrived and was never marked no-show still blocks
    its room, so it has to stay visible instead of falling out of every view."""
    stale = Reservation(
        reference="BK26-STALE1",
        guest_id=seeded["guests"][1].id,
        room_id=seeded["rooms"][2].id,
        check_in_date=TODAY - timedelta(days=4),
        check_out_date=TODAY - timedelta(days=2),
        status=ReservationStatus.CONFIRMED,
        nightly_rate=Decimal("150.00"),
        total_price=Decimal("300.00"),
    )
    db.add(stale)
    await db.commit()

    board = await reception_client.get("/api/v1/reservations/front-desk")
    references = [r["reference"] for r in board.json()["arrivals"]]
    assert "BK26-STALE1" in references


async def test_a_stale_booking_still_counts_as_holding_its_room(
    reception_client, db, seeded
):
    """The room cannot be sold while this booking exists, so the rooms page
    must not describe it as free.

    `upcoming_for_room` filtered on `check_in_date >= today`, so a booking
    whose arrival date had passed was reported as neither current nor upcoming
    while `_assert_room_free` still counted it — a room that looked free and
    refused every booking. The rooms page reads the same thing through a
    reservation search bounded by date, so both are checked here.
    """
    stale = Reservation(
        reference="BK26-STALE2",
        guest_id=seeded["guests"][1].id,
        room_id=seeded["rooms"][2].id,
        check_in_date=TODAY - timedelta(days=4),
        check_out_date=TODAY - timedelta(days=2),
        status=ReservationStatus.CONFIRMED,
        nightly_rate=Decimal("150.00"),
        total_price=Decimal("300.00"),
    )
    db.add(stale)
    await db.commit()

    holder = await ReservationRepository(db).upcoming_for_room(seeded["rooms"][2].id)
    assert holder is not None and holder.reference == "BK26-STALE2"

    unresolved = await reception_client.get(
        "/api/v1/reservations",
        params={"status": "confirmed", "date_to": iso(-1), "order": "asc"},
    )
    assert "BK26-STALE2" in [r["reference"] for r in unresolved.json()["items"]]


# ------------------------------------------------------- cancelling a stay in house
async def _checked_in_stay(client, seeded) -> int:
    booking_response = await book(
        client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=0, check_out=2,
    )
    reservation_id = booking_response.json()["id"]
    checked_in = await client.post(f"/api/v1/reservations/{reservation_id}/check-in")
    assert checked_in.status_code == 200
    return reservation_id


async def _login(client, email: str, password: str) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200


async def test_a_receptionist_cannot_cancel_a_stay_that_is_checked_in(
    reception_client, seeded
):
    """Cancelling an in-house stay removed the nights from occupancy, the money
    from the dashboard, and blocked any later payment — a free room with no
    trace. Marking a no-show, which destroys far less, was already manager-only.
    """
    reservation_id = await _checked_in_stay(reception_client, seeded)

    response = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/cancel", json={"reason": "oops"}
    )
    assert response.status_code == 403

    unchanged = await reception_client.get(f"/api/v1/reservations/{reservation_id}")
    assert unchanged.json()["status"] == "checked_in"


async def test_a_manager_must_write_off_the_balance_to_cancel_an_in_house_stay(
    reception_client, seeded
):
    reservation_id = await _checked_in_stay(reception_client, seeded)
    await _login(reception_client, "manager@test.az", "Manager1234")

    refused = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/cancel", json={"reason": "goodwill"}
    )
    assert refused.status_code == 409
    assert "owes" in refused.json()["error"]["message"]

    waived = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/cancel",
        json={"reason": "goodwill", "waive_balance": True},
    )
    assert waived.status_code == 200
    body = waived.json()
    assert body["status"] == "cancelled"
    # 2 nights x 150.00 + 18% VAT
    assert float(body["waived_amount"]) == 354.00
    assert body["waived_at"] is not None
