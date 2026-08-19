"""Regression tests for the security review.

Every test here corresponds to a hole that was open at some point — each one
fails if the guard protecting it is removed.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.core.ratelimit import failed_logins

pytestmark = pytest.mark.asyncio

TODAY = date.today()


def iso(days_from_today: int) -> str:
    return (TODAY + timedelta(days=days_from_today)).isoformat()


def booking(guest_id: int, room_id: int, **extra) -> dict:
    return {
        "guest_id": guest_id,
        "room_id": room_id,
        "check_in_date": iso(1),
        "check_out_date": iso(3),
        "adults": 1,
        **extra,
    }


# ------------------------------------------------- rate override (escalation)
async def test_receptionist_cannot_override_the_nightly_rate(reception_client, seeded):
    response = await reception_client.post(
        "/api/v1/reservations",
        json=booking(seeded["guests"][0].id, seeded["rooms"][1].id, nightly_rate="1.00"),
    )
    assert response.status_code == 403


async def test_receptionist_cannot_override_the_rate_on_a_walk_in(
    reception_client, seeded
):
    response = await reception_client.post(
        "/api/v1/reservations/walk-in",
        json={
            "guest": {
                "full_name": "Walk In",
                "phone": "+994500000009",
                "document_number": "P9000009",
            },
            "room_id": seeded["rooms"][1].id,
            "check_in_date": iso(1),
            "check_out_date": iso(3),
            "adults": 1,
            "nightly_rate": "1.00",
        },
    )
    assert response.status_code == 403


async def test_receptionist_cannot_override_the_rate_when_editing(
    reception_client, seeded
):
    created = await reception_client.post(
        "/api/v1/reservations",
        json=booking(seeded["guests"][0].id, seeded["rooms"][1].id),
    )
    assert created.status_code == 201

    response = await reception_client.patch(
        f"/api/v1/reservations/{created.json()['id']}",
        json={"nightly_rate": "1.00"},
    )
    assert response.status_code == 403


async def test_manager_may_still_override_the_nightly_rate(manager_client, seeded):
    response = await manager_client.post(
        "/api/v1/reservations",
        json=booking(seeded["guests"][0].id, seeded["rooms"][1].id, nightly_rate="99.00"),
    )
    assert response.status_code == 201
    assert float(response.json()["nightly_rate"]) == 99.00


async def test_receptionist_can_still_book_at_the_standard_rate(
    reception_client, seeded
):
    response = await reception_client.post(
        "/api/v1/reservations",
        json=booking(seeded["guests"][0].id, seeded["rooms"][1].id),
    )
    assert response.status_code == 201
    assert float(response.json()["nightly_rate"]) == 150.00


# ------------------------------------------------------------- session expiry
async def test_changing_the_password_signs_other_devices_out(client: AsyncClient):
    other = await client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.az", "password": "Manager1234"},
    )
    stolen = other.json()["access_token"]
    header = {"Authorization": f"Bearer {stolen}"}
    assert (await client.get("/api/v1/auth/me", headers=header)).status_code == 200

    await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Manager1234", "new_password": "BrandNew1234"},
    )

    assert (await client.get("/api/v1/auth/me", headers=header)).status_code == 401


async def test_changing_the_password_keeps_the_current_session(client: AsyncClient):
    await client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.az", "password": "Manager1234"},
    )
    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Manager1234", "new_password": "BrandNew1234"},
    )
    assert changed.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_new_password_must_differ_from_the_old_one(manager_client: AsyncClient):
    response = await manager_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Manager1234", "new_password": "Manager1234"},
    )
    assert response.status_code == 422


# ----------------------------------------------------------- last admin lockout
async def test_the_last_admin_cannot_be_demoted(admin_client, seeded):
    response = await admin_client.patch(
        f"/api/v1/staff/{seeded['admin'].id}", json={"role": "receptionist"}
    )
    assert response.status_code == 409


async def test_the_last_admin_cannot_be_deactivated_by_patch(admin_client, seeded):
    response = await admin_client.patch(
        f"/api/v1/staff/{seeded['admin'].id}", json={"is_active": False}
    )
    assert response.status_code == 409


async def test_a_second_admin_can_be_demoted(admin_client, seeded):
    created = await admin_client.post(
        "/api/v1/staff",
        json={
            "full_name": "Second Admin",
            "email": "second@test.az",
            "password": "SecondAdmin1",
            "role": "admin",
        },
    )
    assert created.status_code == 201

    response = await admin_client.patch(
        f"/api/v1/staff/{created.json()['id']}", json={"role": "receptionist"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "receptionist"


# ------------------------------------------------------------ password policy
@pytest.mark.parametrize(
    "weak",
    ["short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"],
)
async def test_weak_staff_passwords_are_rejected(admin_client, weak):
    response = await admin_client.post(
        "/api/v1/staff",
        json={
            "full_name": "Weak Password",
            "email": "weak@test.az",
            "password": weak,
            "role": "receptionist",
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------- brute force
async def test_repeated_failed_logins_are_rate_limited(client: AsyncClient):
    statuses = []
    for _ in range(15):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.az", "password": "wrong-password"},
        )
        statuses.append(response.status_code)

    assert 429 in statuses, "login endpoint accepted 15 rapid attempts without throttling"


# -------------------------------------------------------------- input typing
async def test_walk_in_rejects_a_malformed_guest_with_422(reception_client, seeded):
    response = await reception_client.post(
        "/api/v1/reservations/walk-in",
        json={
            "guest": {"full_name": "X"},  # too short, and no phone or document
            "room_id": seeded["rooms"][1].id,
            "check_in_date": iso(1),
            "check_out_date": iso(3),
        },
    )
    assert response.status_code == 422


# ----------------------------------------------------------- response headers
async def test_security_headers_are_present(client: AsyncClient):
    headers = (await client.get("/health")).headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "no-store" in headers["Cache-Control"]


async def test_health_does_not_leak_the_environment(client: AsyncClient):
    assert (await client.get("/health")).json() == {"status": "ok"}


# ----------------------------------------------------------- invoice rendering
@pytest.mark.parametrize(
    "hostile_name",
    ["<b>Bold Guest", "Smith & Sons", "a < b", "</para>Broken"],
    ids=["open-tag", "ampersand", "bare-lt", "closing-tag"],
)
async def test_invoice_pdf_survives_markup_in_a_guest_name(
    reception_client, seeded, hostile_name
):
    """ReportLab parses Paragraph text as mini-XML.

    An unescaped name used to raise a parse error, which made that guest's
    invoice permanently un-generatable.
    """
    guest = await reception_client.post(
        "/api/v1/guests",
        json={
            "full_name": hostile_name,
            "phone": "+994500000123",
            "document_number": f"HOSTILE{abs(hash(hostile_name)) % 10000}",
        },
    )
    assert guest.status_code == 201

    created = await reception_client.post(
        "/api/v1/reservations",
        json=booking(guest.json()["id"], seeded["rooms"][1].id),
    )
    assert created.status_code == 201

    issued = await reception_client.post(
        f"/api/v1/invoices/reservation/{created.json()['id']}"
    )
    assert issued.status_code == 201

    pdf = await reception_client.get(
        f"/api/v1/invoices/reservation/{created.json()['id']}/pdf"
    )
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


# ------------------------------------------------------------- search wildcards
async def test_a_percent_search_does_not_match_every_guest(reception_client):
    """`%` is a LIKE wildcard; unescaped it returned the whole table."""
    everything = await reception_client.get("/api/v1/guests")
    assert everything.json()["total"] > 0

    wildcard = await reception_client.get("/api/v1/guests", params={"q": "%"})
    assert wildcard.json()["total"] == 0


async def test_an_underscore_search_does_not_match_every_guest(reception_client):
    wildcard = await reception_client.get("/api/v1/guests", params={"q": "_"})
    assert wildcard.json()["total"] == 0


async def test_search_still_finds_a_real_guest(reception_client, seeded):
    found = await reception_client.get("/api/v1/guests", params={"q": "Alice"})
    assert found.json()["total"] == 1


# ------------------------------------------------------------- session revocation
async def test_signing_out_revokes_the_token(reception_client):
    """Logout used to delete the cookie and nothing else.

    The JWT stayed valid for its full 12 hours and `Authorization: Bearer`
    accepts it, so anything that captured the token once kept full access long
    after the user believed they had signed out.
    """
    token = reception_client.cookies.get("hotel_access_token")
    assert token

    still_valid = await reception_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert still_valid.status_code == 200

    signed_out = await reception_client.post("/api/v1/auth/logout")
    assert signed_out.status_code == 200

    replayed = await reception_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert replayed.status_code == 401, "the token must stop working at sign-out"


async def test_the_account_locks_after_repeated_failures(client, monkeypatch):
    """The per-IP limit does not stop a botnet spreading its attempts, so
    failures are counted per account as well."""
    monkeypatch.setattr(failed_logins, "threshold", 3)

    for _ in range(3):
        wrong = await client.post(
            "/api/v1/auth/login",
            json={"email": "reception@test.az", "password": "WrongPassword1"},
        )
        assert wrong.status_code == 401

    locked = await client.post(
        "/api/v1/auth/login",
        json={"email": "reception@test.az", "password": "Reception1234"},
    )
    assert locked.status_code == 401, "the right password must not open a locked account"
    assert locked.json()["error"]["message"] == "Incorrect email or password.", (
        "the lockout must not become the account-enumeration oracle that the "
        "identical login message exists to prevent"
    )

    # A different address is unaffected — the lock is per account, not global.
    other = await client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.az", "password": "Manager1234"},
    )
    assert other.status_code == 200


# ------------------------------------------------------- waiving what is owed
async def test_a_receptionist_cannot_check_out_with_a_balance(reception_client, seeded):
    """`allow_outstanding_balance` was a query parameter the lowest role could
    set, and nothing recorded that the money had been given up."""
    created = await reception_client.post(
        "/api/v1/reservations",
        json=booking(seeded["guests"][0].id, seeded["rooms"][1].id, check_in_date=iso(0)),
    )
    reservation_id = created.json()["id"]
    await reception_client.post(f"/api/v1/reservations/{reservation_id}/check-in")

    refused = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-out",
        params={"allow_outstanding_balance": True},
    )
    assert refused.status_code == 403

    await reception_client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.az", "password": "Manager1234"},
    )
    allowed = await reception_client.post(
        f"/api/v1/reservations/{reservation_id}/check-out",
        params={"allow_outstanding_balance": True},
    )
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["status"] == "checked_out"
    assert float(body["waived_amount"]) > 0, "the waiver has to be recorded"
    assert body["waived_at"] is not None


# --------------------------------------------------------------- guest deletion
async def test_deleting_a_guest_with_history_is_refused(reception_client, seeded):
    """This endpoint answered 500 for every guest — `Guest.reservations` is
    lazy-loaded and touching it outside greenlet context raised MissingGreenlet.
    Fixing only the crash would have been worse: the guard let a *completed*
    stay through, and the relationship cascades to payments and invoices.
    """
    created = await reception_client.post(
        "/api/v1/reservations",
        json=booking(seeded["guests"][0].id, seeded["rooms"][1].id),
    )
    assert created.status_code == 201

    await reception_client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.az", "password": "Manager1234"},
    )
    response = await reception_client.delete(f"/api/v1/guests/{seeded['guests'][0].id}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_deleting_a_guest_without_history_works(reception_client):
    fresh = await reception_client.post(
        "/api/v1/guests",
        json={
            "full_name": "Never Stayed",
            "phone": "+994500000777",
            "document_number": "P9000777",
        },
    )
    guest_id = fresh.json()["id"]

    await reception_client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.az", "password": "Manager1234"},
    )
    deleted = await reception_client.delete(f"/api/v1/guests/{guest_id}")
    assert deleted.status_code == 200
    assert (await reception_client.get(f"/api/v1/guests/{guest_id}")).status_code == 404
