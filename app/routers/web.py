"""Server-rendered pages. Data is fetched by the browser from the JSON API."""

from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.deps import DbSession, OptionalUser
from app.models.user import UserRole
from app.services.room_service import RoomService

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(include_in_schema=False)


_ASSETS = (
    BASE_DIR / "static" / "css" / "app.css",
    BASE_DIR / "static" / "js" / "app.js",
)


def _asset_version() -> str:
    """Cache-buster for /static — StaticFiles serves those with a long cache."""
    stamps = [f.stat().st_mtime_ns for f in _ASSETS if f.exists()]
    return f"{max(stamps, default=0):x}"


# Recomputed per request only in development, where the files change under a
# running server; in production the mtimes are fixed at boot.
_ASSET_VERSION = _asset_version()


def _context(request: Request, user, **extra) -> dict:
    """Everything base.html needs, plus per-page extras."""
    return {
        "request": request,
        "user": user,
        "asset_version": (
            _asset_version() if settings.APP_ENV == "development" else _ASSET_VERSION
        ),
        "app_name": settings.APP_NAME,
        "currency": settings.CURRENCY,
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "tax_rate": settings.TAX_RATE,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
        "is_manager": user.role in (UserRole.ADMIN, UserRole.MANAGER) if user else False,
        "is_admin": user.role == UserRole.ADMIN if user else False,
        **extra,
    }


def _redirect_to_login(path: str) -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={path}", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: OptionalUser):
    if user is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html", _context(request, None, page="login")
    )


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request, user: OptionalUser):
    if user is None:
        return _redirect_to_login("/")
    return templates.TemplateResponse(
        "dashboard.html", _context(request, user, page="dashboard")
    )


@router.get("/front-desk", response_class=HTMLResponse)
async def front_desk_page(request: Request, user: OptionalUser):
    if user is None:
        return _redirect_to_login("/front-desk")
    return templates.TemplateResponse(
        "frontdesk.html", _context(request, user, page="front-desk")
    )


@router.get("/rooms", response_class=HTMLResponse)
async def rooms_page(request: Request, user: OptionalUser, db: DbSession):
    if user is None:
        return _redirect_to_login("/rooms")
    room_types = await RoomService(db).list_types()
    return templates.TemplateResponse(
        "rooms.html",
        _context(request, user, page="rooms", room_types=room_types),
    )


@router.get("/guests", response_class=HTMLResponse)
async def guests_page(request: Request, user: OptionalUser):
    if user is None:
        return _redirect_to_login("/guests")
    return templates.TemplateResponse(
        "guests.html", _context(request, user, page="guests")
    )


@router.get("/reservations", response_class=HTMLResponse)
async def reservations_page(request: Request, user: OptionalUser):
    if user is None:
        return _redirect_to_login("/reservations")
    return templates.TemplateResponse(
        "reservations.html", _context(request, user, page="reservations")
    )


@router.get("/reservations/new", response_class=HTMLResponse)
async def new_reservation_page(request: Request, user: OptionalUser, db: DbSession):
    if user is None:
        return _redirect_to_login("/reservations/new")
    room_types = await RoomService(db).list_types()
    return templates.TemplateResponse(
        "new_reservation.html",
        _context(request, user, page="new-reservation", room_types=room_types),
    )


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, user: OptionalUser):
    if user is None:
        return _redirect_to_login("/reports")
    if user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "reports.html", _context(request, user, page="reports")
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user: OptionalUser):
    if user is None:
        return _redirect_to_login("/settings")
    return templates.TemplateResponse(
        "settings.html", _context(request, user, page="settings")
    )
