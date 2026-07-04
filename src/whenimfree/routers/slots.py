"""Slot CRUD routes."""

import json
from datetime import date
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..auth import get_current_user
from ..db import get_db
from ..utils import format_time, templates

router = APIRouter()


async def _conflict_check(db, user_id: int, start: str, end: str):
    """Return the first accepted booking that overlaps [start, end), or None."""
    return await (await db.execute(
        "SELECT guest_name, requested_start, requested_end FROM booking_requests"
        " WHERE slot_owner_id=? AND status='accepted'"
        " AND requested_start < ? AND requested_end > ?",
        (user_id, end, start)
    )).fetchone()


def _conflict_error_html(conflict) -> HTMLResponse:
    name  = conflict["guest_name"]
    start = format_time(conflict["requested_start"])
    end   = format_time(conflict["requested_end"])
    resp = HTMLResponse(
        f'<div class="bg-red-50 text-red-600 text-sm px-4 py-3 rounded-xl">'
        f'Conflicts with {name}\'s confirmed booking ({start}–{end}).</div>'
    )
    resp.headers["HX-Retarget"] = "#modal-error"
    resp.headers["HX-Reswap"]   = "innerHTML"
    return resp


def _edit_conflict_error_html(conflict) -> HTMLResponse:
    name  = conflict["guest_name"]
    start = format_time(conflict["requested_start"])
    end   = format_time(conflict["requested_end"])
    resp = HTMLResponse(
        f'<div class="bg-red-50 text-red-600 text-sm px-4 py-3 rounded-xl">'
        f'Conflicts with {name}\'s confirmed booking ({start}–{end}).</div>'
    )
    resp.headers["HX-Retarget"] = "#edit-error"
    resp.headers["HX-Reswap"]   = "innerHTML"
    return resp


@router.post("/slots", response_class=HTMLResponse)
async def create_slot(request: Request, start_time: str = Form(...), end_time: str = Form(...),
                      cal_month: str = Form(""), cal_year: str = Form("")):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)

    if end_time <= start_time:
        if request.headers.get("HX-Request"):
            resp = HTMLResponse('<div class="bg-red-50 text-red-600 text-sm px-4 py-3 rounded-xl mt-2">End time must be after start.</div>')
            resp.headers["HX-Retarget"] = "#modal-error"
            resp.headers["HX-Reswap"] = "innerHTML"
            return resp
        return RedirectResponse("/dashboard?error=invalid_times", status_code=302)

    db = await get_db()
    try:
        conflict = await _conflict_check(db, user["id"], start_time, end_time)
        if conflict:
            return _conflict_error_html(conflict)

        await db.execute(
            "INSERT INTO availability_slots (user_id, start_time, end_time) VALUES (?, ?, ?)",
            (user["id"], start_time, end_time),
        )
        await db.commit()
    finally:
        await db.close()

    if request.headers.get("HX-Request"):
        return await _dashboard_response(request, user, cal_month, cal_year, extra_triggers=["slotsAdded"])
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/slots/bulk", response_class=HTMLResponse)
async def create_slots_bulk(request: Request, blocks: str = Form(...),
                            cal_month: str = Form(""), cal_year: str = Form("")):
    user = await get_current_user(request)
    if not user:
        return Response(status_code=401)

    try:
        items = json.loads(blocks)
    except (TypeError, ValueError):
        items = []
    valid = [b for b in items if isinstance(b, dict) and b.get("start_time") and b.get("end_time")
             and b["end_time"] > b["start_time"]]

    if not valid:
        if request.headers.get("HX-Request"):
            resp = HTMLResponse('<div class="bg-red-50 text-red-600 text-sm px-4 py-3 rounded-xl mt-2">Add at least one valid time block.</div>')
            resp.headers["HX-Retarget"] = "#modal-error"
            resp.headers["HX-Reswap"] = "innerHTML"
            return resp
        return RedirectResponse("/dashboard?error=invalid_times", status_code=302)

    db = await get_db()
    try:
        for b in valid:
            conflict = await _conflict_check(db, user["id"], b["start_time"], b["end_time"])
            if conflict:
                return _conflict_error_html(conflict)

        for b in valid:
            await db.execute(
                "INSERT INTO availability_slots (user_id, start_time, end_time) VALUES (?, ?, ?)",
                (user["id"], b["start_time"], b["end_time"]),
            )
        await db.commit()
    finally:
        await db.close()

    if request.headers.get("HX-Request"):
        return await _dashboard_response(request, user, cal_month, cal_year, extra_triggers=["slotsAdded"])
    return RedirectResponse("/dashboard", status_code=302)


@router.delete("/slots/{slot_id}")
async def delete_slot(request: Request, slot_id: int):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    db = await get_db()
    try:
        await db.execute("DELETE FROM availability_slots WHERE id = ? AND user_id = ?", (slot_id, user["id"]))
        await db.commit()
    finally:
        await db.close()

    if request.headers.get("HX-Request"):
        return await _dashboard_response(request, user)
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/slots/{slot_id}/edit")
async def edit_slot(request: Request, slot_id: int,
                    start_time: str = Form(...), end_time: str = Form(...),
                    cal_month: str = Form(""), cal_year: str = Form("")):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)

    db = await get_db()
    try:
        conflict = await _conflict_check(db, user["id"], start_time, end_time)
        if conflict:
            return _edit_conflict_error_html(conflict)

        await db.execute(
            "UPDATE availability_slots SET start_time = ?, end_time = ? WHERE id = ? AND user_id = ?",
            (start_time, end_time, slot_id, user["id"]),
        )
        await db.commit()
    finally:
        await db.close()

    if request.headers.get("HX-Request"):
        return await _dashboard_response(request, user, cal_month, cal_year, extra_triggers=["closeModal"])
    return RedirectResponse("/dashboard", status_code=302)


async def _dashboard_response(request, user, month=None, year=None, extra_triggers=None):
    from ..db import get_db
    from ..services.calendar import _build_calendar

    today = date.today()
    m = int(month or request.query_params.get("month") or today.month)
    y = int(year or request.query_params.get("year") or today.year)

    db = await get_db()
    try:
        slots = [dict(r) for r in await (await db.execute(
            "SELECT * FROM availability_slots WHERE user_id=? AND (status IS NULL OR status='available')"
            " ORDER BY start_time", (user["id"],)
        )).fetchall()]
        recurring = [dict(r) for r in await (await db.execute(
            "SELECT * FROM recurring_slots WHERE user_id=? ORDER BY dows, start_hhmm", (user["id"],)
        )).fetchall()]
        bookings = [dict(r) for r in await (await db.execute(
            "SELECT * FROM booking_requests WHERE slot_owner_id=? AND status='accepted'"
            " AND strftime('%Y-%m', requested_start)=?",
            (user["id"], f"{y}-{m:02d}")
        )).fetchall()]
    finally:
        await db.close()

    blocked_times = {(b["requested_start"], b["requested_end"]) for b in bookings}
    cal = _build_calendar(y, m, slots, recurring, bookings=bookings, blocked_times=blocked_times)

    from ..config import settings
    resp = templates.TemplateResponse(request, "partials/_dashboard_wrapper.html", {
        "request": request, "slots": slots, "recurring": recurring, "user": user,
        "month": m, "year": y, "cal": cal, "base_url": settings.BASE_URL,
    })
    triggers = ["closeModal"] + (extra_triggers or [])
    resp.headers["HX-Trigger"] = ",".join(triggers)
    return resp
