"""REST API v1 router aggregation."""

from fastapi import APIRouter

from app.routers.api import auth, guests, payments, reports, reservations, rooms

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(auth.staff_router)
api_router.include_router(guests.router)
api_router.include_router(rooms.router)
api_router.include_router(rooms.types_router)
api_router.include_router(reservations.router)
api_router.include_router(payments.router)
api_router.include_router(payments.invoices_router)
api_router.include_router(reports.router)

__all__ = ["api_router"]
