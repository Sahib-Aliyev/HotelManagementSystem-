"""Regression tests for the security review.

Every test here corresponds to a hole that was open at some point — each one
fails if the guard protecting it is removed.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

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
