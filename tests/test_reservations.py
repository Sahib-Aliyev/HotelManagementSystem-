"""Booking rules — above all, that a room is never sold twice for one night."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

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
    total = float(booking.json()["total_price"])

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

    await reception_client.post(
        "/api/v1/payments",
        json={
            "reservation_id": reservation_id,
            "amount": total,
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
    await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-out",
        params={"allow_outstanding_balance": True},
    )

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
    assert float(folio["balance_due"]) == 300.00

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
    assert float(folio["balance_due"]) == 150.00


async def test_invoice_pdf_is_generated(reception_client, seeded):
    booking = await book(
        reception_client, guest_id=seeded["guests"][0].id,
        room_id=seeded["rooms"][1].id, check_in=1, check_out=3,
    )
    response = await reception_client.get(
        f"/api/v1/invoices/reservation/{booking.json()['id']}/pdf"
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


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
