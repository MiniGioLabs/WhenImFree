"""Booking request routes (owner-side: view, accept, decline)."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from ..auth import get_current_user
from ..db import get_db
from ..utils import render

router = APIRouter()


async def _requests_html(db, user_id: int, request: Request, status: str = "all") -> HTMLResponse:
    if status == "pending":
        where = "AND status='pending'"
    elif status == "accepted":
        where = "AND status='accepted'"
    elif status == "declined":
        where = "AND status='declined'"
    else:
        status = "all"
        where = ""

    reqs = [dict(r) for r in await (await db.execute(
        f"""SELECT * FROM booking_requests WHERE slot_owner_id=? {where}
            ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC""",
        (user_id,)
    )).fetchall()]

    counts = dict(await (await db.execute(
        """SELECT
            SUM(1) AS total,
            SUM(status='pending') AS pending,
            SUM(status='accepted') AS accepted,
            SUM(status='declined') AS declined
           FROM booking_requests WHERE slot_owner_id=?""",
        (user_id,)
    )).fetchone())
    total_count    = counts["total"]    or 0
    pending_count  = counts["pending"]  or 0
    accepted_count = counts["accepted"] or 0
    declined_count = counts["declined"] or 0

    return render(request, "partials/_requests.html",
                  booking_requests=reqs,
                  status_filter=status,
                  total_count=total_count,
                  pending_count=pending_count,
                  accepted_count=accepted_count,
                  declined_count=declined_count)


async def _split_slot_on_accept(db, owner_id: int, req_start: str, req_end: str) -> None:
    """
    When an accepted booking covers part (or all) of an availability window, split the window:
    - One-off slot: mark it booked, insert any head/tail remainder as new available slots.
    - Recurring occurrence: insert head/tail as new one-off available slots; the recurring
      occurrence itself is blocked at display time via the accepted booking_request overlap check.
    """
    # --- One-off slot path ---
    slot = await (await db.execute(
        "SELECT * FROM availability_slots WHERE user_id=? AND start_time <= ? AND end_time >= ?"
        " AND (status IS NULL OR status='available')",
        (owner_id, req_start, req_end)
    )).fetchone()

    if slot:
        slot = dict(slot)
        await db.execute("UPDATE availability_slots SET status='booked' WHERE id=?", (slot["id"],))
        if slot["start_time"] < req_start:
            await db.execute(
                "INSERT INTO availability_slots (user_id, start_time, end_time, status) VALUES (?,?,?,'available')",
                (owner_id, slot["start_time"], req_start)
            )
        if req_end < slot["end_time"]:
            await db.execute(
                "INSERT INTO availability_slots (user_id, start_time, end_time, status) VALUES (?,?,?,'available')",
                (owner_id, req_end, slot["end_time"])
            )
        return

    # --- Recurring slot path ---
    from ..services.calendar import _expand_recurring
    req_date = req_start[:10]
    year, month = int(req_date[:4]), int(req_date[5:7])
    recurring = [dict(r) for r in await (await db.execute(
        "SELECT * FROM recurring_slots WHERE user_id=? AND active=1", (owner_id,)
    )).fetchall()]

    for occ in _expand_recurring(recurring, year, month):
        if (occ["start_time"][:10] == req_date
                and occ["start_time"] <= req_start
                and occ["end_time"] >= req_end):
            # Occurrence found; insert one-off remainder slots for the host's remaining availability
            if occ["start_time"] < req_start:
                await db.execute(
                    "INSERT INTO availability_slots (user_id, start_time, end_time, status) VALUES (?,?,?,'available')",
                    (owner_id, occ["start_time"], req_start)
                )
            if req_end < occ["end_time"]:
                await db.execute(
                    "INSERT INTO availability_slots (user_id, start_time, end_time, status) VALUES (?,?,?,'available')",
                    (owner_id, req_end, occ["end_time"])
                )
            break


@router.get("/dashboard/requests", response_class=HTMLResponse)
async def dashboard_requests(request: Request, status: str = Query("all")):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    db = await get_db()
    try:
        return await _requests_html(db, user["id"], request, status)
    finally:
        await db.close()


@router.post("/requests/{request_id}/accept", response_class=HTMLResponse)
async def accept_request(request: Request, request_id: int):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    db = await get_db()
    try:
        req_row = await (await db.execute(
            "SELECT * FROM booking_requests WHERE id=? AND slot_owner_id=?",
            (request_id, user["id"])
        )).fetchone()
        if not req_row:
            raise HTTPException(status_code=404)
        req_row = dict(req_row)

        await db.execute(
            "UPDATE booking_requests SET status='accepted' WHERE id=?", (request_id,)
        )
        await _split_slot_on_accept(db, user["id"], req_row["requested_start"], req_row["requested_end"])
        await db.commit()
        return await _requests_html(db, user["id"], request, "all")
    finally:
        await db.close()


@router.post("/requests/{request_id}/decline", response_class=HTMLResponse)
async def decline_request(request: Request, request_id: int):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    db = await get_db()
    try:
        await db.execute(
            "UPDATE booking_requests SET status='declined' WHERE id=? AND slot_owner_id=?",
            (request_id, user["id"])
        )
        await db.commit()
        return await _requests_html(db, user["id"], request, "all")
    finally:
        await db.close()
