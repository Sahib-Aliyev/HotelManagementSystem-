"""Dashboard and reporting endpoints."""

from datetime import date, timedelta

from fastapi import APIRouter, Query

from app.core.deps import DbSession, ManagerUser, StaffUser
from app.schemas.report import (
    DashboardPayload,
    OccupancyPoint,
    ReportPayload,
    TimeSeriesPoint,
)
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/dashboard", response_model=DashboardPayload)
async def dashboard(db: DbSession, _user: StaffUser):
    return await ReportService(db).dashboard()


@router.get("/revenue-trend", response_model=list[TimeSeriesPoint])
async def revenue_trend(
    db: DbSession, _user: StaffUser, days: int = Query(14, ge=2, le=90)
):
    return await ReportService(db).revenue_trend(days)


@router.get("/occupancy-trend", response_model=list[OccupancyPoint])
async def occupancy_trend(
    db: DbSession, _user: StaffUser, days: int = Query(14, ge=2, le=90)
):
    return await ReportService(db).occupancy_trend(days)


@router.get("/summary", response_model=ReportPayload)
async def summary(
    db: DbSession,
    _manager: ManagerUser,
    start: date | None = None,
    end: date | None = None,
):
    """Full management report. Defaults to the last 30 days."""
    end = end or date.today()
    start = start or end - timedelta(days=29)
    return await ReportService(db).report(start, end)
