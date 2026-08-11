"""Application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.database import create_all, engine
from app.core.exceptions import register_exception_handlers
from app.routers.api import api_router
from app.routers.web import router as web_router

BASE_DIR = Path(__file__).resolve().parent

limiter = Limiter(key_func=get_remote_address, default_limits=[])


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
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    return response


@app.get("/health", tags=["System"], include_in_schema=False)
async def health():
    return JSONResponse({"status": "ok", "environment": settings.APP_ENV})
