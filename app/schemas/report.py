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
    period_start: date
    period_end: date
    total_revenue: Decimal
    total_bookings: int
    total_nights: int
    average_daily_rate: Decimal
    average_occupancy: float
    revenue_series: list[TimeSeriesPoint]
    occupancy_series: list[OccupancyPoint]
    room_type_performance: list[RoomTypePerformance]
    payment_method_split: list[TimeSeriesPoint]
