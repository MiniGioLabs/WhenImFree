"""Dashboard routes."""

from datetime import date
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth import get_current_user
from ..db import get_db
from ..services.calendar import _build_calendar
from ..utils import render

router = APIRouter()


async def _fetch_recurring(db, user_id: int) -> list:
    return [dict(r) for r in await (await db.execute(
        "SELECT * FROM recurring_slots WHERE user_id=? ORDER BY dows, start_hhmm", (user_id,)
    )).fetchall()]


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, month: int = Query(None), year: int = Query(None)):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    today = date.today()
    month = month or today.month
    year = year or today.year
    if month < 1: month = 12; year -= 1
    if month > 12: month = 1; year += 1

    db = await get_db()
    try:
        user_row = await db.execute("SELECT * FROM users WHERE id=?", (user["id"],))
        user = dict(await user_row.fetchone())
        slots = [dict(r) for r in await (await db.execute(
            "SELECT * FROM availability_slots WHERE user_id=? AND (status IS NULL OR status='available') ORDER BY start_time",
            (user["id"],)
        )).fetchall()]
        recurring = await _fetch_recurring(db, user["id"])
        bookings = [dict(r) for r in await (await db.execute(
            "SELECT * FROM booking_requests WHERE slot_owner_id=? AND status='accepted'"
            " AND strftime('%Y-%m', requested_start)=?",
            (user["id"], f"{year}-{month:02d}")
        )).fetchall()]
    finally:
        await db.close()

    blocked_times = {(b["requested_start"], b["requested_end"]) for b in bookings}
    cal = _build_calendar(year, month, slots, recurring, bookings=bookings, blocked_times=blocked_times)

    from ..config import settings
    return render(request, "dashboard.html", user=user, slots=slots, recurring=recurring,
                  cal=cal, month=month, year=year, base_url=settings.BASE_URL)


@router.get("/dashboard/calendar", response_class=HTMLResponse)
async def dashboard_calendar(request: Request, month: int = Query(None), year: int = Query(None)):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)

    today = date.today()
    month = month or today.month
    year = year or today.year
    if month < 1: month = 12; year -= 1
    if month > 12: month = 1; year += 1

    db = await get_db()
    try:
        slots = [dict(r) for r in await (await db.execute(
            "SELECT * FROM availability_slots WHERE user_id=? AND (status IS NULL OR status='available') ORDER BY start_time",
            (user["id"],)
        )).fetchall()]
        recurring = await _fetch_recurring(db, user["id"])
        bookings = [dict(r) for r in await (await db.execute(
            "SELECT * FROM booking_requests WHERE slot_owner_id=? AND status='accepted'"
            " AND strftime('%Y-%m', requested_start)=?",
            (user["id"], f"{year}-{month:02d}")
        )).fetchall()]
    finally:
        await db.close()

    blocked_times = {(b["requested_start"], b["requested_end"]) for b in bookings}
    cal = _build_calendar(year, month, slots, recurring, bookings=bookings, blocked_times=blocked_times)
    return render(request, "partials/calendar.html", cal=cal, month=month, year=year)
