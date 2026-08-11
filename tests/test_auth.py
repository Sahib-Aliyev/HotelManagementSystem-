"""Authentication and authorisation."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_login_succeeds_with_correct_credentials(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.az", "password": "Admin1234"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_sets_session_cookie(client: AsyncClient):
    await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.az", "password": "Admin1234"},
    )
    assert "hotel_access_token" in client.cookies


async def test_login_rejects_wrong_password(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.az", "password": "not-the-password"},
    )
    assert response.status_code == 401


async def test_login_error_does_not_reveal_whether_email_exists(client: AsyncClient):
    known = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.az", "password": "wrong"},
    )
    unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.az", "password": "wrong"},
    )
    assert known.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_protected_endpoint_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_receptionist_cannot_reach_manager_reports(reception_client: AsyncClient):
    response = await reception_client.get("/api/v1/reports/summary")
    assert response.status_code == 403


async def test_manager_can_reach_reports(manager_client: AsyncClient):
    response = await manager_client.get("/api/v1/reports/summary")
    assert response.status_code == 200


async def test_receptionist_cannot_create_staff(reception_client: AsyncClient):
    response = await reception_client.post(
        "/api/v1/staff",
        json={
            "full_name": "Sneaky Admin",
            "email": "sneaky@test.az",
            "password": "Password123",
            "role": "admin",
        },
    )
    assert response.status_code == 403


async def test_logout_clears_the_session(reception_client: AsyncClient):
    assert (await reception_client.get("/api/v1/auth/me")).status_code == 200
    await reception_client.post("/api/v1/auth/logout")
    assert (await reception_client.get("/api/v1/auth/me")).status_code == 401
