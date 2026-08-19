"""Dashboard metrics and management reports."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.payment import Payment
from app.models.reservation import BLOCKING_STATUSES, Reservation, ReservationStatus
from app.models.room import Room, RoomStatus, RoomType
from app.repositories.payment_repo import (
    PaymentRepository,
    is_cash_movement,
    signed_amount,
)
from app.repositories.reservation_repo import ReservationRepository
from app.repositories.room_repo import RoomRepository
from app.schemas.report import (
    DashboardPayload,
    DashboardStats,
    OccupancyPoint,
    ReportPayload,
    RoomTypePerformance,
    TimeSeriesPoint,
)

CENTS = Decimal("0.01")
MAX_REPORT_DAYS = 366


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.rooms = RoomRepository(db)
        self.reservations = ReservationRepository(db)
        self.payments = PaymentRepository(db)

    # ------------------------------------------------------------- dashboard
    async def dashboard(self) -> DashboardPayload:
        today = date.today()
        month_start = today.replace(day=1)

        arrivals = await self.reservations.arrivals_on(today)
        departures = await self.reservations.departures_on(today)
        in_house = await self.reservations.in_house()

        status_counts = await self.rooms.status_counts()
        rooms_total = sum(status_counts.values())
        rooms_occupied = await self.rooms.occupied_on(today)
        out_of_service = status_counts.get(RoomStatus.MAINTENANCE, 0)
        sellable = max(rooms_total - out_of_service, 0)

        stats = DashboardStats(
            arrivals_today=len(arrivals),
            departures_today=len(departures),
            in_house_guests=sum(r.guest_count for r in in_house),
            rooms_total=rooms_total,
            rooms_occupied=rooms_occupied,
            rooms_available=max(sellable - rooms_occupied, 0),
            rooms_out_of_service=out_of_service,
            occupancy_rate=round(rooms_occupied / sellable * 100, 1) if sellable else 0.0,
            revenue_today=await self.payments.revenue_between(today, today),
            revenue_month=await self.payments.revenue_between(month_start, today),
            outstanding_balance=await self._outstanding_balance(),
            pending_reservations=await self.reservations.count_by_status(
                ReservationStatus.PENDING
            ),
        )

        return DashboardPayload(
            stats=stats,
            arrivals=arrivals,
            departures=departures,
            in_house=in_house,
        )

    async def _outstanding_balance(self) -> Decimal:
        """Unpaid portion of every reservation that is not cancelled, VAT included.

        `Reservation.total_price` is net of tax, so summing it against payments
        under-reported what the hotel is owed by the whole VAT share and
        disagreed with the folio of every single reservation. The multiplier
        below is the aggregate form of `pricing.total_due()`.
        """
        vat_multiplier = Decimal("1") + Decimal(str(settings.TAX_RATE))
        paid_subq = (
            select(
                Payment.reservation_id.label("rid"),
                func.coalesce(func.sum(signed_amount()), 0).label("paid"),
            )
            .where(is_cash_movement())
            .group_by(Payment.reservation_id)
            .subquery()
        )
        stmt = (
            select(
                func.coalesce(
                    func.sum(
                        Reservation.total_price * vat_multiplier
                        - func.coalesce(paid_subq.c.paid, 0)
                    ),
                    0,
                )
            )
            .select_from(Reservation)
            .outerjoin(paid_subq, paid_subq.c.rid == Reservation.id)
            .where(
                Reservation.status.notin_(
                    [ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW]
                )
            )
        )
        total = Decimal(str((await self.db.execute(stmt)).scalar_one()))
        return max(total, Decimal("0")).quantize(CENTS)

    # ----------------------------------------------------------- 30-day trend
    async def revenue_trend(self, days: int = 14) -> list[TimeSeriesPoint]:
        end = date.today()
        start = end - timedelta(days=days - 1)
        by_day = await self.payments.revenue_by_day(start, end)
        points = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            points.append(
                TimeSeriesPoint(
                    label=day.strftime("%d %b"),
                    value=by_day.get(day, Decimal("0")).quantize(CENTS),
                )
            )
        return points

    async def occupancy_trend(self, days: int = 14) -> list[OccupancyPoint]:
        end = date.today()
        start = end - timedelta(days=days - 1)
        counts = await self.rooms.status_counts()
        total = max(sum(counts.values()) - counts.get(RoomStatus.MAINTENANCE, 0), 0)

        points = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            occupied = await self.rooms.occupied_on(day)
            points.append(
                OccupancyPoint(
                    day=day,
                    occupied=occupied,
                    total=total,
                    rate=round(occupied / total * 100, 1) if total else 0.0,
                )
            )
        return points

    # --------------------------------------------------------------- reports
    async def report(self, start: date, end: date) -> ReportPayload:
        if end < start:
            raise ValidationError("The end date must not precede the start date.")
        if (end - start).days > MAX_REPORT_DAYS:
            raise ValidationError(
                f"Reporting periods are limited to {MAX_REPORT_DAYS} days."
            )

        days = (end - start).days + 1
        total_revenue = await self.payments.revenue_between(start, end)

        # Bookings whose stay overlaps the period and that were not written off.
        stmt = select(Reservation).where(
            Reservation.check_in_date <= end,
            Reservation.check_out_date >= start,
            Reservation.status.notin_(
                [ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW]
            ),
        )
        reservations = list((await self.db.execute(stmt)).unique().scalars())

        total_nights = 0
        for reservation in reservations:
            # Count only the nights that fall inside the reporting window.
            first = max(reservation.check_in_date, start)
            last = min(reservation.check_out_date, end + timedelta(days=1))
            total_nights += max((last - first).days, 0)

        adr = (
            (total_revenue / total_nights).quantize(CENTS)
            if total_nights
            else Decimal("0.00")
        )

        counts = await self.rooms.status_counts()
        sellable = max(sum(counts.values()) - counts.get(RoomStatus.MAINTENANCE, 0), 0)
        room_nights_available = sellable * days
        average_occupancy = (
            round(total_nights / room_nights_available * 100, 1)
            if room_nights_available
            else 0.0
        )

        by_day = await self.payments.revenue_by_day(start, end)
        revenue_series = [
            TimeSeriesPoint(
                label=(start + timedelta(days=i)).strftime("%d %b"),
                value=by_day.get(start + timedelta(days=i), Decimal("0")).quantize(CENTS),
            )
            for i in range(days)
        ]

        occupancy_series = []
        for i in range(days):
            day = start + timedelta(days=i)
            occupied = await self.rooms.occupied_on(day)
            occupancy_series.append(
                OccupancyPoint(
                    day=day,
                    occupied=occupied,
                    total=sellable,
                    rate=round(occupied / sellable * 100, 1) if sellable else 0.0,
                )
            )

        method_split = [
            TimeSeriesPoint(label=method, value=amount)
            for method, amount in (
                await self.payments.revenue_by_method(start, end)
            ).items()
        ]

        return ReportPayload(
            period_start=start,
            period_end=end,
            total_revenue=total_revenue,
            total_bookings=len(reservations),
            total_nights=total_nights,
            average_daily_rate=adr,
            average_occupancy=average_occupancy,
            revenue_series=revenue_series,
            occupancy_series=occupancy_series,
            room_type_performance=await self._room_type_performance(start, end),
            payment_method_split=method_split,
        )

    async def _room_type_performance(
        self, start: date, end: date
    ) -> list[RoomTypePerformance]:
        stmt = (
            select(
                RoomType.name,
                func.count(Reservation.id),
                func.coalesce(func.sum(Reservation.total_price), 0),
            )
            .select_from(Reservation)
            .join(Room, Reservation.room_id == Room.id)
            .join(RoomType, Room.room_type_id == RoomType.id)
            .where(
                Reservation.check_in_date <= end,
                Reservation.check_out_date >= start,
                Reservation.status.notin_(
                    [ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW]
                ),
            )
            .group_by(RoomType.name)
            .order_by(func.coalesce(func.sum(Reservation.total_price), 0).desc())
        )
        rows = (await self.db.execute(stmt)).all()

        # Nights are derived per reservation, so fetch them alongside.
        nights_stmt = (
            select(
                RoomType.name,
                Reservation.check_in_date,
                Reservation.check_out_date,
            )
            .select_from(Reservation)
            .join(Room, Reservation.room_id == Room.id)
            .join(RoomType, Room.room_type_id == RoomType.id)
            .where(
                Reservation.check_in_date <= end,
                Reservation.check_out_date >= start,
                Reservation.status.notin_(
                    [ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW]
                ),
            )
        )
        nights_by_type: dict[str, int] = {}
        for name, check_in, check_out in (await self.db.execute(nights_stmt)).all():
            first = max(check_in, start)
            last = min(check_out, end + timedelta(days=1))
            nights_by_type[name] = nights_by_type.get(name, 0) + max(
                (last - first).days, 0
            )

        return [
            RoomTypePerformance(
                room_type=name,
                bookings=int(bookings),
                nights_sold=nights_by_type.get(name, 0),
                revenue=Decimal(str(revenue)).quantize(CENTS),
            )
            for name, bookings, revenue in rows
        ]

    async def occupancy_snapshot(self) -> dict:
        counts = await self.rooms.status_counts()
        return {status.value: count for status, count in counts.items()}
