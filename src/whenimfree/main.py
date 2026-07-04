"""WhenImFree — FastAPI app entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .limiter import limiter
from .utils import render, templates, static_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if settings.SECRET_KEY in ("replace-me", ""):
    logger.warning("SECRET_KEY is set to an insecure default — set a random value in .env before deploying")

if settings.POSTHOG_API_KEY:
    import posthog
    posthog.api_key = settings.POSTHOG_API_KEY
    posthog.host = settings.POSTHOG_HOST
    logger.info("PostHog configured")
else:
    posthog = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .db import init_db
    await init_db()
    yield


app = FastAPI(title="WhenImFree", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="whenimfree",
    same_site="lax",
    https_only=settings.HTTPS_ONLY,
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        if request.headers.get("HX-Request"):
            return HTMLResponse("<p class='text-sm text-gray-400 text-center py-4'>Not found.</p>", status_code=404)
        return HTMLResponse(
            """<!doctype html><html><head><title>Not Found — WhenImFree</title>
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <script src="https://cdn.tailwindcss.com"></script>
            <script>tailwind.config={theme:{extend:{colors:{brand:'#FF6B6B','brand-dark':'#E55555'}}}}</script>
            </head>
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
        """<!doctype html><html><head><title>Slow down — WhenImFree</title>
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
async def track_pageviews(request: Request, call_next):
    response = await call_next(request)
    if settings.posthog_configured:
        user_id = request.session.get("user_id", "anonymous")
        posthog.capture(str(user_id), "$pageview", {
            "$current_url": str(request.url),
            "$pathname": request.url.path,
        })
    return response


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
            """<!doctype html><html><head><title>Error — WhenImFree</title>
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="min-h-screen flex items-center justify-center bg-gray-50">
            <div class="text-center p-8">
                <div class="text-5xl mb-4">😬</div>
                <h1 class="text-2xl font-bold mb-2">Something went wrong</h1>
                <p class="text-gray-500 mb-6">We hit an unexpected error. Try refreshing the page.</p>
                <a href="/dashboard" class="text-brand underline text-sm">Back to dashboard</a>
            </div></body></html>""",
            status_code=500,
        )


from .routers import auth, dashboard, slots, profile, recurring, requests as requests_router
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(slots.router)
app.include_router(profile.router)
app.include_router(recurring.router)
app.include_router(requests_router.router)


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
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


@app.get("/@{username}/calendar", response_class=HTMLResponse)
async def public_profile_calendar(request: Request, username: str, month: int = None, year: int = None):
    from .db import get_db
    from .services.calendar import _build_calendar
    from datetime import date

    today = date.today()
    month = month or today.month
    year = year or today.year
    if month < 1: month = 12; year -= 1
    if month > 12: month = 1; year += 1

    db = await get_db()
    try:
        row = await db.execute("SELECT id FROM users WHERE username = ?", (username.lower(),))
        profile_user = await row.fetchone()
        if not profile_user:
            raise StarletteHTTPException(status_code=404)
        slots = [dict(r) for r in await (await db.execute(
            "SELECT * FROM availability_slots WHERE user_id=? AND (status IS NULL OR status='available')"
            " AND strftime('%Y-%m', start_time)=? ORDER BY start_time",
            (profile_user["id"], f"{year}-{month:02d}")
        )).fetchall()]
        recurring = [dict(r) for r in await (await db.execute(
            "SELECT * FROM recurring_slots WHERE user_id=? AND active=1 ORDER BY dows, start_hhmm",
            (profile_user["id"],)
        )).fetchall()]
        accepted = [dict(r) for r in await (await db.execute(
            "SELECT requested_start, requested_end FROM booking_requests"
            " WHERE slot_owner_id=? AND status='accepted'"
            " AND strftime('%Y-%m', requested_start)=?",
            (profile_user["id"], f"{year}-{month:02d}")
        )).fetchall()]
    finally:
        await db.close()

    blocked_times = {(b["requested_start"], b["requested_end"]) for b in accepted}
    cal = _build_calendar(year, month, slots, recurring, blocked_times=blocked_times)
    return render(request, "partials/_profile_calendar.html",
                  cal=cal, month=month, year=year,
                  username=username,
                  today_month=today.month, today_year=today.year,
                  today_str=today.isoformat())


@app.post("/@{username}/request", response_class=HTMLResponse)
@limiter.limit("5/hour")
async def submit_request(
    request: Request,
    username: str,
    guest_name: str = Form(...),
    guest_phone: str = Form(...),
    requested_start: str = Form(...),
    requested_end: str = Form(...),
    note: str = Form(""),
):
    from .auth import normalize_phone
    from .db import get_db

    guest_name = guest_name.strip()
    note = note.strip()[:200]
    normalized = normalize_phone(guest_phone)

    if not guest_name or len(guest_name) > 40:
        return HTMLResponse("Name must be 1–40 characters.", status_code=422)
    if not normalized:
        return HTMLResponse("Enter a valid 10-digit US phone number.", status_code=422)
    if requested_start >= requested_end:
        return HTMLResponse("End time must be after start time.", status_code=422)

    db = await get_db()
    try:
        row = await db.execute("SELECT id, name, phone FROM users WHERE username=?", (username.lower(),))
        owner = await row.fetchone()
        if not owner:
            raise StarletteHTTPException(status_code=404)

        if normalized == owner["phone"]:
            return HTMLResponse("You can't send a request to yourself.", status_code=422)

        # Validate the requested time falls within an available window
        one_off = await (await db.execute(
            "SELECT id FROM availability_slots WHERE user_id=? AND start_time <= ? AND end_time >= ?"
            " AND (status IS NULL OR status='available')",
            (owner["id"], requested_start, requested_end)
        )).fetchone()

        if not one_off:
            # Check recurring slots for a covering occurrence
            from .services.calendar import _expand_recurring
            req_date = requested_start[:10]
            year_r, month_r = int(req_date[:4]), int(req_date[5:7])
            rec_rows = [dict(r) for r in await (await db.execute(
                "SELECT * FROM recurring_slots WHERE user_id=? AND active=1", (owner["id"],)
            )).fetchall()]
            covered = any(
                occ["start_time"][:10] == req_date
                and occ["start_time"] <= requested_start
                and occ["end_time"] >= requested_end
                for occ in _expand_recurring(rec_rows, year_r, month_r)
            )
            if not covered:
                return HTMLResponse("That time is no longer available.", status_code=422)

        # Conflict check: reject if overlapping with an already-accepted booking
        conflict = await (await db.execute(
            "SELECT id FROM booking_requests WHERE slot_owner_id=? AND status='accepted'"
            " AND requested_start < ? AND requested_end > ?",
            (owner["id"], requested_end, requested_start)
        )).fetchone()
        if conflict:
            return HTMLResponse("That time overlaps with an existing booking.", status_code=422)

        pending = await (await db.execute(
            "SELECT COUNT(*) FROM booking_requests WHERE slot_owner_id=? AND guest_phone=? AND status='pending'",
            (owner["id"], normalized),
        )).fetchone()
        if pending[0] >= 3:
            return HTMLResponse("You already have 3 pending requests — wait for a response first.", status_code=429)

        await db.execute(
            "INSERT INTO booking_requests (slot_owner_id, guest_name, guest_phone, requested_start, requested_end, note) VALUES (?,?,?,?,?,?)",
            (owner["id"], guest_name, normalized, requested_start, requested_end, note),
        )
        await db.commit()
    finally:
        await db.close()

    first = owner["name"].split()[0]
    return HTMLResponse(f"""
        <div class="text-center py-6 pop-in">
            <div class="text-4xl mb-3">🎉</div>
            <p class="font-black text-gray-800 mb-1">Request sent!</p>
            <p class="text-sm text-gray-500">{first} will text you to confirm.</p>
        </div>
    """)


@app.get("/@{username}", response_class=HTMLResponse)
async def public_profile(request: Request, username: str):
    from .db import get_db
    from .services.calendar import _build_calendar, _expand_recurring
    from datetime import date

    db = await get_db()
    try:
        row = await db.execute("SELECT id, username, name, avatar_url FROM users WHERE username = ?", (username.lower(),))
        profile_user = await row.fetchone()
        if not profile_user:
            raise StarletteHTTPException(status_code=404)
        profile_user = dict(profile_user)

        slots = [dict(r) for r in await (await db.execute(
            "SELECT * FROM availability_slots WHERE user_id=? AND start_time >= datetime('now')"
            " AND (status IS NULL OR status='available') ORDER BY start_time",
            (profile_user["id"],)
        )).fetchall()]
        recurring = [dict(r) for r in await (await db.execute(
            "SELECT * FROM recurring_slots WHERE user_id=? AND active=1 ORDER BY dows, start_hhmm",
            (profile_user["id"],)
        )).fetchall()]
        accepted = [dict(r) for r in await (await db.execute(
            "SELECT requested_start, requested_end FROM booking_requests"
            " WHERE slot_owner_id=? AND status='accepted'",
            (profile_user["id"],)
        )).fetchall()]
    finally:
        await db.close()

    today = date.today()
    blocked_times = {(b["requested_start"], b["requested_end"]) for b in accepted}

    # Expand recurring into concrete upcoming slots (next 4 weeks), skipping blocked occurrences
    from datetime import timedelta
    expanded = []
    for week_offset in range(4):
        ref = today + timedelta(weeks=week_offset)
        expanded += [s for s in _expand_recurring(recurring, ref.year, ref.month)
                     if (s["start_time"], s["end_time"]) not in blocked_times]
    # Deduplicate by date+time and filter past
    seen = set()
    unique_expanded = []
    for s in expanded:
        key = s["start_time"]
        if key not in seen and s["start_time"] >= today.isoformat():
            seen.add(key)
            unique_expanded.append(s)

    all_slots = sorted(slots + unique_expanded, key=lambda x: x["start_time"])
    cal = _build_calendar(today.year, today.month, slots, recurring, blocked_times=blocked_times)
    return render(request, "profile.html", profile_user=profile_user, slots=all_slots,
                  cal=cal, month=today.month, year=today.year,
                  username=username,
                  today_month=today.month, today_year=today.year,
                  today_str=today.isoformat(),
                  base_url=settings.BASE_URL)
