"""Application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.database import create_all, engine
from app.core.exceptions import register_exception_handlers
from app.core.ratelimit import limiter
from app.routers.api import api_router
from app.routers.web import router as web_router

BASE_DIR = Path(__file__).resolve().parent

# The UI pulls Tailwind, Alpine and Chart.js from public CDNs and Tailwind's
# browser build compiles styles at runtime, which is why 'unsafe-inline' and
# 'unsafe-eval' are still here. Vendoring those three files is what removes
# them — see the note in CLAUDE.md.
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # In development the schema is created on boot so the app is usable
    # immediately; production deployments should run `alembic upgrade head`.
    if settings.APP_ENV == "development":
        await create_all()
    yield
    await engine.dispose()


app = FastAPI(
    title=f"{settings.APP_NAME} — Guest Management API",
    description=(
        "Hotel front-office system: guest registration, room inventory, "
        "reservations, check-in/out, payments, invoicing and reporting."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # A public schema hands an attacker the whole endpoint and payload map.
    docs_url="/api/docs" if settings.docs_enabled else None,
    redoc_url="/api/redoc" if settings.docs_enabled else None,
    openapi_url="/api/openapi.json" if settings.docs_enabled else None,
)

# No SlowAPIMiddleware: it only evaluates application-wide default limits,
# which are empty here. The per-route @limiter.limit decorators do the work.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if settings.trusted_host_list != ["*"]:
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    # Narrowed from "*": with credentialed CORS the reflected wildcard would
    # let any allowed origin drive any verb with the session cookie attached.
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

register_exception_handlers(app)

app.mount(
    "/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static"
)

app.include_router(api_router)
app.include_router(web_router)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = CSP
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

    if settings.is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Every page and API response here carries guest PII — passport numbers,
    # phone numbers, addresses. None of it should sit in a shared cache or in
    # the back/forward cache of a shared front-desk browser after sign-out.
    if not request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, private"

    return response


@app.get("/health", tags=["System"], include_in_schema=False)
async def health():
    """Liveness *and* readiness: a check that cannot fail is not a check.

    It used to return a literal, so an orchestrator kept routing traffic to a
    container whose database was unreachable. The reply still says nothing about
    environment, version or the error itself — only whether this instance can
    serve a request.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})
