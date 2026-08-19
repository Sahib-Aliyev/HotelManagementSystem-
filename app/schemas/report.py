"""Dashboard and reporting schemas."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.reservation import ReservationRead


class DashboardStats(BaseModel):
    arrivals_today: int
    departures_today: int
    in_house_guests: int
    rooms_total: int
    rooms_occupied: int
    rooms_available: int
    rooms_out_of_service: int
    occupancy_rate: float
    revenue_today: Decimal
    revenue_month: Decimal
    outstanding_balance: Decimal
    pending_reservations: int


class DashboardPayload(BaseModel):
    stats: DashboardStats
    arrivals: list[ReservationRead]
    departures: list[ReservationRead]
    in_house: list[ReservationRead]


class TimeSeriesPoint(BaseModel):
    label: str
    value: Decimal


class OccupancyPoint(BaseModel):
    day: date
    occupied: int
    total: int
    rate: float


class RoomTypePerformance(BaseModel):
    room_type: str
    bookings: int
    nights_sold: int
    revenue: Decimal


class ReportPayload(BaseModel):
    """A management report on two explicitly separate bases.

    `total_revenue` is **accrual**: the accommodation charge earned by the nights
    consumed inside the period, net of tax. It is what `room_type_performance`
    breaks down and what `average_daily_rate` divides, so the three agree.

    `cash_collected` is **cash**: money that actually arrived in the period,
    refunds deducted and VAT included. A prepayment lands here in the month it is
    taken and in `total_revenue` in the month the guest sleeps.

    The two were once a single `total_revenue` computed the cash way while the
    room-type table beside it was computed the accrual way, so the screen showed
    two irreconcilable revenues and ADR divided one basis by the other's unit.
    """

    period_start: date
    period_end: date
    #: Accrual: nights consumed in the period, at the booked rate, net of tax.
    total_revenue: Decimal
    #: Cash: payments received in the period, refunds deducted, VAT included.
    cash_collected: Decimal
    total_bookings: int
    total_nights: int
    average_daily_rate: Decimal
    average_occupancy: float
    #: Daily cash received — matches `cash_collected`, not `total_revenue`.
    cash_series: list[TimeSeriesPoint]
    occupancy_series: list[OccupancyPoint]
    room_type_performance: list[RoomTypePerformance]
    payment_method_split: list[TimeSeriesPoint]
