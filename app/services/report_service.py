"""Dashboard metrics and management reports."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.payment import Payment
from app.models.reservation import Reservation, ReservationStatus
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
from app.services.pricing import accommodation_charge

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
        """What the hotel is still owed, VAT included and waivers deducted.

        Three things this has to get right, each of which it once got wrong:

        `Reservation.total_price` is net of tax, so summing it against payments
        under-reported the debt by the whole VAT share and disagreed with the
        folio of every reservation. The multiplier below is the aggregate form
        of `pricing.total_due()`.

        A balance a manager formally wrote off is not owed any more. The waiver
        was recorded on the reservation (`waived_amount`) and never read here, so
        the dashboard kept billing the hotel's own management for money it had
        decided to forgo — the one number they read to judge whether the ledger
        balances.

        And the clamp is per reservation, not on the sum. Applied once at the end
        it let an overpaid stay silently cancel out another stay's debt, so two
        errors could hide each other and the total still looked plausible.
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
        owed = (
            Reservation.total_price * vat_multiplier
            - func.coalesce(paid_subq.c.paid, 0)
            - func.coalesce(Reservation.waived_amount, 0)
        )
        stmt = (
            select(func.coalesce(func.sum(case((owed > 0, owed), else_=0)), 0))
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

        # One grouped query, not one per day: this loop used to issue 92
        # statements for a 90-day chart.
        occupied_by_day = await self.rooms.occupied_per_day(start, end)
        return [
            OccupancyPoint(
                day=day,
                occupied=occupied,
                total=total,
                rate=round(occupied / total * 100, 1) if total else 0.0,
            )
            for day, occupied in sorted(occupied_by_day.items())
        ]

    # --------------------------------------------------------------- reports
    async def report(self, start: date, end: date) -> ReportPayload:
        if end < start:
            raise ValidationError("The end date must not precede the start date.")
        if (end - start).days > MAX_REPORT_DAYS:
            raise ValidationError(
                f"Reporting periods are limited to {MAX_REPORT_DAYS} days."
            )

        days = (end - start).days + 1

        # Two different questions, two named figures. `total_revenue` used to be
        # the cash taken in the window while the room-type breakdown on the same
        # screen was accrued accommodation charges, net of tax — so the headline
        # and the table it sits above could never add up, and neither said which
        # it was. Revenue is now accrual throughout: what the nights consumed in
        # this window earned, net of tax, which is the basis occupancy and ADR
        # are already on. Cash collected is still reported, separately and under
        # its own name, because a hotel needs both.
        cash_collected = await self.payments.revenue_between(start, end)

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
        total_revenue = Decimal("0.00")
        for reservation in reservations:
            # Count only the nights that fall inside the reporting window, and
            # earn only those nights' share of the stay.
            first = max(reservation.check_in_date, start)
            last = min(reservation.check_out_date, end + timedelta(days=1))
            nights_in_window = max((last - first).days, 0)
            total_nights += nights_in_window
            total_revenue += accommodation_charge(
                reservation.nightly_rate, nights_in_window
            )
        total_revenue = total_revenue.quantize(CENTS)

        # ADR is room revenue ÷ room-nights sold, net of tax — the figure owners
        # benchmark against the market. Dividing cash received by nights
        # consumed made a prepayment look like a rate rise: a two-night stay
        # paid up front inside a one-night window reported 354.00 for a room
        # sold at 150.00.
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
        cash_series = [
            TimeSeriesPoint(
                label=(start + timedelta(days=i)).strftime("%d %b"),
                value=by_day.get(start + timedelta(days=i), Decimal("0")).quantize(CENTS),
            )
            for i in range(days)
        ]

        occupied_by_day = await self.rooms.occupied_per_day(start, end)
        occupancy_series = [
            OccupancyPoint(
                day=day,
                occupied=occupied,
                total=sellable,
                rate=round(occupied / sellable * 100, 1) if sellable else 0.0,
            )
            for day, occupied in sorted(occupied_by_day.items())
        ]

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
            cash_collected=cash_collected,
            total_bookings=len(reservations),
            total_nights=total_nights,
            average_daily_rate=adr,
            average_occupancy=average_occupancy,
            cash_series=cash_series,
            occupancy_series=occupancy_series,
            room_type_performance=await self._room_type_performance(start, end),
            payment_method_split=method_split,
        )

    async def _room_type_performance(
        self, start: date, end: date
    ) -> list[RoomTypePerformance]:
        """Bookings, nights and revenue per room type — on the same basis as the
        headline figures, so the breakdown adds up to them.

        This used to sum `Reservation.total_price`, the whole stay, while the
        headline counted cash received in the window. Two bases on one screen,
        and the table could not be reconciled with the number above it. Revenue
        here is now the same thing `report()` totals: nights consumed inside the
        window, at the rate agreed on the booking, net of tax. It also used to
        take two queries over the identical row set to get nights and money
        separately; one pass does both.
        """
        stmt = (
            select(
                RoomType.name,
                Reservation.check_in_date,
                Reservation.check_out_date,
                Reservation.nightly_rate,
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

        bookings: dict[str, int] = {}
        nights: dict[str, int] = {}
        revenue: dict[str, Decimal] = {}
        for name, check_in, check_out, rate in (await self.db.execute(stmt)).all():
            first = max(check_in, start)
            last = min(check_out, end + timedelta(days=1))
            nights_in_window = max((last - first).days, 0)
            bookings[name] = bookings.get(name, 0) + 1
            nights[name] = nights.get(name, 0) + nights_in_window
            revenue[name] = revenue.get(name, Decimal("0")) + accommodation_charge(
                rate, nights_in_window
            )

        return sorted(
            (
                RoomTypePerformance(
                    room_type=name,
                    bookings=count,
                    nights_sold=nights.get(name, 0),
                    revenue=revenue.get(name, Decimal("0")).quantize(CENTS),
                )
                for name, count in bookings.items()
            ),
            key=lambda row: row.revenue,
            reverse=True,
        )
