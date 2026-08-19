"""Populate the database with a realistic demo hotel.

    python seed.py           # create tables and seed if empty
    python seed.py --reset   # drop everything first
"""

import asyncio
import random
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, create_all, drop_all
from app.core.security import hash_password
from app.models import (
    DocumentType,
    Guest,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Reservation,
    ReservationStatus,
    Room,
    RoomStatus,
    RoomType,
    User,
    UserRole,
)

# Fixed seed so repeated runs produce the same demo hotel.
RNG = random.Random(20260811)

STAFF = [
    ("Aysel Mammadova", "admin@grandaurora.az", "Admin1234", UserRole.ADMIN, "+994 50 111 11 11"),
    ("Rashad Aliyev", "manager@grandaurora.az", "Manager1234", UserRole.MANAGER, "+994 50 222 22 22"),
    ("Nigar Huseynova", "reception@grandaurora.az", "Reception1234", UserRole.RECEPTIONIST, "+994 50 333 33 33"),
    ("Elvin Qasimov", "elvin@grandaurora.az", "Reception1234", UserRole.RECEPTIONIST, "+994 50 444 44 44"),
]

ROOM_TYPES = [
    ("Standard Single", "Compact room with a queen bed and city view.", "85.00", 1,
     ["Wi-Fi", "Air conditioning", "Smart TV", "Safe"]),
    ("Standard Double", "Comfortable double room with a work desk.", "120.00", 2,
     ["Wi-Fi", "Air conditioning", "Smart TV", "Minibar", "Safe"]),
    ("Deluxe Double", "Spacious room with a balcony and seating area.", "180.00", 3,
     ["Wi-Fi", "Balcony", "Minibar", "Bathrobe", "Nespresso", "Smart TV"]),
    ("Family Room", "Two connected bedrooms, ideal for families.", "240.00", 4,
     ["Wi-Fi", "Two bathrooms", "Minibar", "Sofa bed", "Smart TV"]),
    ("Executive Suite", "Separate living room, panoramic Caspian view.", "420.00", 4,
     ["Wi-Fi", "Living room", "Jacuzzi", "Butler service", "Nespresso", "Lounge access"]),
]

# Rooms per floor, keyed by room-type index.
FLOOR_PLAN = {
    1: [0, 0, 1, 1, 1, 1],
    2: [1, 1, 1, 1, 2, 2],
    3: [1, 1, 2, 2, 2, 3],
    4: [2, 2, 3, 3, 4, 4],
    5: [3, 4, 4, 4],
}

GUESTS = [
    ("Leyla Ibrahimova", "+994 55 123 45 67", "leyla.ib@example.com", "AZ", "AZE9384712", "Azerbaijan", 1988),
    ("Michael Thornton", "+44 7700 900123", "m.thornton@example.co.uk", "GB", "GB4471209", "United Kingdom", 1975),
    ("Sofia Rossi", "+39 340 111 2233", "sofia.rossi@example.it", "IT", "IT8823014", "Italy", 1992),
    ("Kenan Aliyev", "+994 51 987 65 43", "kenan.a@example.com", "AZ", "AZE1128395", "Azerbaijan", 1983),
    ("Anna Kowalski", "+48 601 234 567", "a.kowalski@example.pl", "PL", "PL5590127", "Poland", 1995),
    ("Ahmet Yilmaz", "+90 532 444 5566", "ahmet.y@example.com.tr", "TR", "TR7781340", "Türkiye", 1979),
    ("Fatima Al-Rashid", "+971 50 777 8899", "fatima.ar@example.ae", "AE", "AE3390188", "UAE", 1990),
    ("Hans Müller", "+49 170 5556677", "h.mueller@example.de", "DE", "DE9912047", "Germany", 1968),
    ("Nurana Safarova", "+994 70 333 22 11", "nurana.s@example.com", "AZ", "AZE7745120", "Azerbaijan", 1997),
    ("Chen Wei", "+86 138 0013 8000", "chen.wei@example.cn", "CN", "CN6612903", "China", 1986),
    ("Olga Petrova", "+7 916 555 4433", "o.petrova@example.ru", "RU", "RU4409281", "Russia", 1981),
    ("James Okafor", "+234 802 345 6789", "j.okafor@example.ng", "NG", "NG1123409", "Nigeria", 1993),
    ("Marie Dubois", "+33 6 12 34 56 78", "m.dubois@example.fr", "FR", "FR8890123", "France", 1989),
    ("Tural Nabiyev", "+994 55 888 77 66", "tural.n@example.com", "AZ", "AZE2201938", "Azerbaijan", 1994),
    ("Yuki Tanaka", "+81 90 1234 5678", "y.tanaka@example.jp", "JP", "JP5567012", "Japan", 1991),
]

REQUESTS = [
    None, None, None,
    "High floor, away from the lift.",
    "Late arrival — around 23:00.",
    "Extra pillows and a baby cot.",
    "Quiet room; travelling for work.",
    "Celebrating an anniversary.",
    "Early check-in if possible.",
    "Gluten-free breakfast.",
]


def _utc(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour, RNG.randint(0, 59)), tzinfo=UTC)


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(User).limit(1))).scalars().first():
            print("Database already contains data — nothing to do.")
            print("Run `python seed.py --reset` to rebuild it from scratch.")
            return

        # ------------------------------------------------------------ staff
        users = [
            User(
                full_name=name,
                email=email,
                hashed_password=hash_password(password),
                role=role,
                phone=phone,
            )
            for name, email, password, role, phone in STAFF
        ]
        db.add_all(users)
        await db.flush()

        # -------------------------------------------------------- room types
        room_types = [
            RoomType(
                name=name,
                description=description,
                base_price=Decimal(price),
                capacity=capacity,
                amenities=amenities,
            )
            for name, description, price, capacity, amenities in ROOM_TYPES
        ]
        db.add_all(room_types)
        await db.flush()

        # ------------------------------------------------------------ rooms
        rooms: list[Room] = []
        for floor, type_indexes in FLOOR_PLAN.items():
            for position, type_index in enumerate(type_indexes, start=1):
                rooms.append(
                    Room(
                        room_number=f"{floor}{position:02d}",
                        room_type_id=room_types[type_index].id,
                        floor=floor,
                        status=RoomStatus.AVAILABLE,
                    )
                )
        # A couple of rooms out of action, as in any real hotel.
        rooms[7].status = RoomStatus.MAINTENANCE
        rooms[7].notes = "Air-conditioning unit being replaced."
        rooms[15].status = RoomStatus.CLEANING
        db.add_all(rooms)
        await db.flush()

        # ----------------------------------------------------------- guests
        guests = [
            Guest(
                full_name=name,
                phone=phone,
                email=email,
                document_type=DocumentType.PASSPORT
                if country_code != "AZ"
                else DocumentType.ID_CARD,
                document_number=document,
                nationality=nationality,
                date_of_birth=date(birth_year, RNG.randint(1, 12), RNG.randint(1, 28)),
            )
            for name, phone, email, country_code, document, nationality, birth_year in GUESTS
        ]
        db.add_all(guests)
        await db.flush()

        # ----------------------------------------------------- reservations
        today = date.today()
        reservations: list[Reservation] = []
        payments: list[Payment] = []
        occupied_windows: dict[int, list[tuple[date, date]]] = {}
        reference_seq = 1

        def room_is_free(room_id: int, check_in: date, check_out: date) -> bool:
            for existing_in, existing_out in occupied_windows.get(room_id, []):
                if check_in < existing_out and check_out > existing_in:
                    return False
            return True

        def make_reservation(
            guest: Guest,
            room: Room,
            check_in: date,
            nights: int,
            status: ReservationStatus,
        ) -> Reservation | None:
            nonlocal reference_seq
            check_out = check_in + timedelta(days=nights)
            if room.status == RoomStatus.MAINTENANCE:
                return None
            if status in (
                ReservationStatus.PENDING,
                ReservationStatus.CONFIRMED,
                ReservationStatus.CHECKED_IN,
            ) and not room_is_free(room.id, check_in, check_out):
                return None

            rate = Decimal(room.room_type.base_price)
            reservation = Reservation(
                reference=f"BK26-{reference_seq:04X}",
                guest_id=guest.id,
                room_id=room.id,
                created_by_id=RNG.choice(users).id,
                check_in_date=check_in,
                check_out_date=check_out,
                adults=min(RNG.randint(1, 2), room.room_type.capacity),
                children=0 if room.room_type.capacity < 3 else RNG.choice([0, 0, 1, 2]),
                status=status,
                nightly_rate=rate,
                total_price=(rate * nights).quantize(Decimal("0.01")),
                special_requests=RNG.choice(REQUESTS),
                created_at=_utc(check_in - timedelta(days=RNG.randint(1, 30)), 10),
            )
            reference_seq += 1

            if status in (
                ReservationStatus.PENDING,
                ReservationStatus.CONFIRMED,
                ReservationStatus.CHECKED_IN,
            ):
                occupied_windows.setdefault(room.id, []).append((check_in, check_out))

            if status == ReservationStatus.CHECKED_IN:
                reservation.actual_check_in = _utc(check_in, 15)
            elif status == ReservationStatus.CHECKED_OUT:
                reservation.actual_check_in = _utc(check_in, 15)
                reservation.actual_check_out = _utc(check_out, 11)
            elif status == ReservationStatus.CANCELLED:
                reservation.cancelled_at = _utc(check_in - timedelta(days=2), 12)
                reservation.cancellation_reason = RNG.choice(
                    ["Change of travel plans.", "Booked elsewhere.", "Flight cancelled."]
                )
            return reservation

        # --- past stays: 45 days of history, fully paid --------------------
        for day_offset in range(45, 0, -1):
            check_in = today - timedelta(days=day_offset)
            for _ in range(RNG.randint(1, 4)):
                room = RNG.choice(rooms)
                nights = RNG.choice([1, 1, 2, 2, 3, 4])
                if check_in + timedelta(days=nights) > today:
                    continue
                reservation = make_reservation(
                    RNG.choice(guests), room, check_in, nights, ReservationStatus.CHECKED_OUT
                )
                if reservation is None:
                    continue
                reservations.append(reservation)

        # --- a handful of cancellations ------------------------------------
        for _ in range(6):
            check_in = today - timedelta(days=RNG.randint(1, 30))
            reservation = make_reservation(
                RNG.choice(guests), RNG.choice(rooms), check_in,
                RNG.randint(1, 3), ReservationStatus.CANCELLED,
            )
            if reservation:
                reservations.append(reservation)

        # --- in-house guests ----------------------------------------------
        for _ in range(8):
            check_in = today - timedelta(days=RNG.randint(1, 3))
            nights = RNG.randint(3, 7)
            if check_in + timedelta(days=nights) <= today:
                nights = (today - check_in).days + RNG.randint(1, 3)
            reservation = make_reservation(
                RNG.choice(guests), RNG.choice(rooms), check_in, nights,
                ReservationStatus.CHECKED_IN,
            )
            if reservation:
                reservations.append(reservation)

        # --- departures due today -----------------------------------------
        for _ in range(3):
            nights = RNG.randint(2, 4)
            check_in = today - timedelta(days=nights)
            reservation = make_reservation(
                RNG.choice(guests), RNG.choice(rooms), check_in, nights,
                ReservationStatus.CHECKED_IN,
            )
            if reservation:
                reservations.append(reservation)

        # --- arrivals today ------------------------------------------------
        for _ in range(5):
            reservation = make_reservation(
                RNG.choice(guests), RNG.choice(rooms), today,
                RNG.choice([1, 2, 2, 3, 5]), ReservationStatus.CONFIRMED,
            )
            if reservation:
                reservations.append(reservation)

        # --- future bookings ----------------------------------------------
        for day_offset in range(1, 40):
            check_in = today + timedelta(days=day_offset)
            for _ in range(RNG.randint(0, 3)):
                status = (
                    ReservationStatus.PENDING
                    if RNG.random() < 0.18
                    else ReservationStatus.CONFIRMED
                )
                reservation = make_reservation(
                    RNG.choice(guests), RNG.choice(rooms), check_in,
                    RNG.choice([1, 2, 2, 3, 4, 7]), status,
                )
                if reservation:
                    reservations.append(reservation)

        db.add_all(reservations)
        await db.flush()

        # Mark rooms holding an in-house guest as occupied.
        for reservation in reservations:
            if reservation.status == ReservationStatus.CHECKED_IN:
                reservation.room.status = RoomStatus.OCCUPIED

        # -------------------------------------------------------- payments
        for reservation in reservations:
            if reservation.status == ReservationStatus.CANCELLED:
                continue

            total = Decimal(reservation.total_price)

            if reservation.status == ReservationStatus.CHECKED_OUT:
                # Settled in full on the day of departure.
                payments.append(
                    Payment(
                        reservation_id=reservation.id,
                        amount=total,
                        method=RNG.choice(list(PaymentMethod)),
                        status=PaymentStatus.PAID,
                        paid_at=_utc(reservation.check_out_date, 11),
                        note="Settled at check-out.",
                    )
                )
            elif reservation.status == ReservationStatus.CHECKED_IN:
                # Most in-house guests have paid a deposit.
                roll = RNG.random()
                if roll < 0.5:
                    payments.append(
                        Payment(
                            reservation_id=reservation.id,
                            amount=total,
                            method=RNG.choice(list(PaymentMethod)),
                            status=PaymentStatus.PAID,
                            paid_at=_utc(reservation.check_in_date, 15),
                            note="Paid in advance.",
                        )
                    )
                elif roll < 0.85:
                    deposit = (total * Decimal("0.5")).quantize(Decimal("0.01"))
                    payments.append(
                        Payment(
                            reservation_id=reservation.id,
                            amount=deposit,
                            method=PaymentMethod.CARD,
                            status=PaymentStatus.PAID,
                            paid_at=_utc(reservation.check_in_date, 15),
                            note="50% deposit.",
                        )
                    )
            elif reservation.status == ReservationStatus.CONFIRMED and RNG.random() < 0.35:
                deposit = (total * Decimal("0.3")).quantize(Decimal("0.01"))
                payments.append(
                    Payment(
                        reservation_id=reservation.id,
                        amount=deposit,
                        method=PaymentMethod.ONLINE,
                        status=PaymentStatus.PAID,
                        paid_at=_utc(min(reservation.check_in_date, today), 12),
                        note="Online prepayment.",
                    )
                )

        db.add_all(payments)
        await db.commit()

        print(f"Seeded {len(users)} staff accounts")
        print(f"Seeded {len(room_types)} room types across {len(rooms)} rooms")
        print(f"Seeded {len(guests)} guests")
        print(f"Seeded {len(reservations)} reservations")
        print(f"Seeded {len(payments)} payments")
        print()
        print("Sign in with:")
        for _name, email, password, role, _phone in STAFF[:3]:
            print(f"  {role.value:<13} {email:<28} {password}")


async def main() -> None:
    reset = "--reset" in sys.argv
    if reset:
        print("Dropping every table…")
        await drop_all()
    await create_all()
    await seed()


if __name__ == "__main__":
    asyncio.run(main())
