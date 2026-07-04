"""Recurring schedule routes."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from ..auth import get_current_user
from ..db import get_db
from ..utils import templates

router = APIRouter()


async def _schedule_response(db, user_id: int, request: Request, trigger: str = None) -> HTMLResponse:
    recurring = [dict(r) for r in await (await db.execute(
        "SELECT * FROM recurring_slots WHERE user_id = ? ORDER BY dows, start_hhmm", (user_id,)
    )).fetchall()]
    resp = templates.TemplateResponse(request, "partials/_schedule_list.html", {
        "request": request,
        "recurring": recurring,
    })
    if trigger:
        resp.headers["HX-Trigger"] = trigger
    return resp


@router.get("/recurring/list", response_class=HTMLResponse)
async def list_recurring(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    db = await get_db()
    try:
        return await _schedule_response(db, user["id"], request)
    finally:
        await db.close()


@router.post("/recurring", response_class=HTMLResponse)
async def create_recurring(
    request: Request,
    dows: str = Form(...),
    start_hhmm: str = Form(...),
    end_hhmm: str = Form(...),
    label: str = Form(""),
):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)

    try:
        dow_list = sorted({int(d) for d in dows.split(",") if d.strip().isdigit()})
        assert dow_list and all(0 <= d <= 6 for d in dow_list)
    except (ValueError, AssertionError):
        raise HTTPException(status_code=422, detail="Invalid days")

    if end_hhmm <= start_hhmm:
        return HTMLResponse(
            '<p class="text-red-500 text-xs py-1 text-center">End time must be after start.</p>'
        )

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO recurring_slots (user_id, dows, start_hhmm, end_hhmm, label) VALUES (?,?,?,?,?)",
            (user["id"], ",".join(str(d) for d in dow_list), start_hhmm, end_hhmm, label.strip() or None),
        )
        await db.commit()
        return await _schedule_response(db, user["id"], request, trigger="refreshCalendar,slotsAdded")
    finally:
        await db.close()


@router.delete("/recurring/{rule_id}", response_class=HTMLResponse)
async def delete_recurring(request: Request, rule_id: int):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM recurring_slots WHERE id=? AND user_id=?", (rule_id, user["id"])
        )
        await db.commit()
        return await _schedule_response(db, user["id"], request, trigger="refreshCalendar")
    finally:
        await db.close()


@router.post("/recurring/{rule_id}/toggle", response_class=HTMLResponse)
async def toggle_recurring(request: Request, rule_id: int):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    db = await get_db()
    try:
        await db.execute(
            "UPDATE recurring_slots SET active = 1 - active WHERE id=? AND user_id=?",
            (rule_id, user["id"]),
        )
        await db.commit()
        return await _schedule_response(db, user["id"], request, trigger="refreshCalendar")
    finally:
        await db.close()
