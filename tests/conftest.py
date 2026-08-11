"""Test fixtures: an isolated in-memory database and an authenticated client."""

from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models import Guest, Room, RoomType, User, UserRole

TEST_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    # StaticPool keeps one connection alive so the in-memory schema survives.
    test_engine = create_async_engine(
        TEST_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db: AsyncSession) -> dict:
    """A minimal hotel: three staff roles, two room types, three rooms, two guests."""
    admin = User(
        full_name="Test Admin", email="admin@test.az",
        hashed_password=hash_password("Admin1234"), role=UserRole.ADMIN,
    )
    manager = User(
        full_name="Test Manager", email="manager@test.az",
        hashed_password=hash_password("Manager1234"), role=UserRole.MANAGER,
    )
    reception = User(
        full_name="Test Reception", email="reception@test.az",
        hashed_password=hash_password("Reception1234"), role=UserRole.RECEPTIONIST,
    )
    db.add_all([admin, manager, reception])

    single = RoomType(
        name="Single", base_price=Decimal("100.00"), capacity=1, amenities=["Wi-Fi"]
    )
    double = RoomType(
        name="Double", base_price=Decimal("150.00"), capacity=2, amenities=["Wi-Fi", "TV"]
    )
    db.add_all([single, double])
    await db.flush()

    rooms = [
        Room(room_number="101", room_type_id=single.id, floor=1),
        Room(room_number="102", room_type_id=double.id, floor=1),
        Room(room_number="103", room_type_id=double.id, floor=1),
    ]
    guests = [
        Guest(full_name="Alice Tester", phone="+994500000001", document_number="P1000001"),
        Guest(full_name="Bob Tester", phone="+994500000002", document_number="P1000002"),
    ]
    db.add_all(rooms + guests)
    await db.commit()

    return {
        "admin": admin, "manager": manager, "reception": reception,
        "single": single, "double": double,
        "rooms": rooms, "guests": guests,
    }


@pytest_asyncio.fixture
async def client(session_factory, seeded) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def reception_client(client: AsyncClient) -> AsyncClient:
    await client.post(
        "/api/v1/auth/login",
        json={"email": "reception@test.az", "password": "Reception1234"},
    )
    return client


@pytest_asyncio.fixture
async def manager_client(client: AsyncClient) -> AsyncClient:
    await client.post(
        "/api/v1/auth/login",
        json={"email": "manager@test.az", "password": "Manager1234"},
    )
    return client
