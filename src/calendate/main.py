"""CalenDate — FastAPI app entry point. Cal.com-inspired scheduling."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import stripe
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .limiter import limiter
from .utils import render, templates, static_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if settings.SECRET_KEY in ("replace-me", "calendate-super-secret-key-2024", ""):
    logger.warning("SECRET_KEY is set to an insecure default — set a random value in .env before deploying")

if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .db import init_db
    await init_db()
    yield


app = FastAPI(title="CalenDate", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="calendate",
    same_site="lax",
    https_only=settings.HTTPS_ONLY,
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        if request.headers.get("HX-Request"):
            return HTMLResponse("<p class='text-sm text-gray-400 text-center py-4'>Not found.</p>", status_code=404)
        return HTMLResponse(
            """<!doctype html><html><head><title>Not Found — CalenDate</title>
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <link rel="stylesheet" href="/static/output.css"></head>
            <body class="min-h-screen flex items-center justify-center bg-gray-50">
            <div class="text-center p-8">
                <div class="text-5xl mb-4">🔍</div>
                <h1 class="text-2xl font-bold mb-2">Page not found</h1>
                <p class="text-gray-500 mb-6">That link doesn't exist or may have expired.</p>
                <a href="/" class="text-brand underline text-sm">Back to home</a>
            </div></body></html>""",
            status_code=404,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    if request.headers.get("HX-Request"):
        return HTMLResponse(
            '<p class="text-sm text-red-500 text-center py-2">Too many requests — wait a moment and try again.</p>',
            status_code=429,
        )
    return HTMLResponse(
        """<!doctype html><html><head><title>Slow down — CalenDate</title>
        <meta name="viewport" content="width=device-width,initial-scale=1"></head>
        <body class="min-h-screen flex items-center justify-center bg-gray-50">
        <div class="text-center p-8">
            <div class="text-5xl mb-4">🐢</div>
            <h1 class="text-2xl font-bold mb-2">Too many requests</h1>
            <p class="text-gray-500">Take a breather and try again in a minute.</p>
        </div></body></html>""",
        status_code=429,
    )

static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.middleware("http")
async def catch_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
        if request.headers.get("HX-Request"):
            return HTMLResponse(
                '<div class="bg-red-50 text-red-600 text-sm px-4 py-3 rounded-xl">Something went wrong. Please try again.</div>',
                status_code=500,
            )
        return HTMLResponse(
            """<!doctype html><html><head><title>Error — CalenDate</title>
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <link rel="stylesheet" href="/static/output.css"></head>
            <body class="min-h-screen flex items-center justify-center bg-gray-50">
            <div class="text-center p-8">
                <div class="text-5xl mb-4">😬</div>
                <h1 class="text-2xl font-bold mb-2">Something went wrong</h1>
                <p class="text-gray-500 mb-6">We hit an unexpected error. Try refreshing the page.</p>
                <a href="/dashboard" class="text-brand underline text-sm">Back to dashboard</a>
            </div></body></html>""",
            status_code=500,
        )


from .routers import auth, dashboard, slots, booking, requests, profile
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(slots.router)
app.include_router(booking.router)
app.include_router(requests.router)
app.include_router(profile.router)


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return render(request, "landing.html")


@app.get("/health")
async def health():
    from .db import get_db
    db = await get_db()
    try:
        await db.execute("SELECT 1")
        return {"status": "ok"}
    finally:
        await db.close()
