"""Public booking page — Cal.com style."""

from datetime import date
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

import stripe
from ..auth import generate_token, normalize_phone
from ..config import settings
from ..config import settings
from ..db import get_db
from ..limiter import limiter
from ..services.calendar import _build_booking_calendar, _free_time_ranges
from ..utils import render, send_sms

router = APIRouter()


async def _booked_by_slot(db, slots: list) -> dict:
    """Map slot_id -> list of its approved bookings, for free-time calculation."""
    slot_ids = [s["id"] for s in slots]
    if not slot_ids:
        return {}
    placeholders = ",".join("?" for _ in slot_ids)
    rows = [dict(r) for r in await (await db.execute(
        f"SELECT slot_id, proposed_start, proposed_end FROM date_requests "
        f"WHERE slot_id IN ({placeholders}) AND status='approved'", slot_ids
    )).fetchall()]
    booked_by_slot: dict = {}
    for r in rows:
        booked_by_slot.setdefault(r["slot_id"], []).append(r)
    return booked_by_slot


@router.get("/book/{token}", response_class=HTMLResponse)
async def booking_page(request: Request, token: str):
    """Cal.com-style public booking page."""
    db = await get_db()
    try:
        user = await (await db.execute(
            "SELECT * FROM users WHERE booking_slug = ?", (token,)
        )).fetchone()
        if not user:
            user = await (await db.execute(
                "SELECT u.* FROM availability_slots a JOIN users u ON a.user_id=u.id WHERE a.token=?", (token,)
            )).fetchone()
        if not user:
            return HTMLResponse(
                "<div class='text-center py-20'><h1 class='text-2xl font-bold'>Link not found</h1></div>"
            )

        user = dict(user)
        slots = [dict(r) for r in await (await db.execute(
            "SELECT * FROM availability_slots WHERE user_id=? ORDER BY start_time", (user["id"],)
        )).fetchall()]
        booked_by_slot = await _booked_by_slot(db, slots)
    finally:
        await db.close()

    cal = _build_booking_calendar(slots, booked_by_slot=booked_by_slot)
    return render(request, "booking.html", host=user, slots=slots, cal=cal, token=user["booking_slug"])


@router.get("/book/{token}/calendar", response_class=HTMLResponse)
async def booking_calendar(request: Request, token: str,
                           month: int = Query(None), year: int = Query(None)):
    """Month navigation for the public booking calendar."""
    db = await get_db()
    try:
        user = await (await db.execute(
            "SELECT * FROM users WHERE booking_slug = ?", (token,)
        )).fetchone()
        if not user:
            return HTMLResponse(
                "<div class='text-center py-20'><h1 class='text-2xl font-bold'>Link not found</h1></div>"
            )
        user = dict(user)
        slots = [dict(r) for r in await (await db.execute(
            "SELECT * FROM availability_slots WHERE user_id=? ORDER BY start_time", (user["id"],)
        )).fetchall()]
        booked_by_slot = await _booked_by_slot(db, slots)
    finally:
        await db.close()

    cal = _build_booking_calendar(slots, booked_by_slot=booked_by_slot, year=year, month=month)
    return render(request, "partials/_booking_calendar.html", cal=cal, token=token)


@router.get("/book/{token}/day", response_class=HTMLResponse)
async def booking_day(request: Request, token: str):
    """Show free time windows for a specific day."""
    date_str = request.query_params.get("date", "")
    db = await get_db()
    try:
        user = await (await db.execute("SELECT * FROM users WHERE booking_slug=?", (token,))).fetchone()
        if not user:
            return HTMLResponse("<p class='text-sm text-red-500'>Not found.</p>")
        user = dict(user)

        slots = [dict(r) for r in await (await db.execute(
            "SELECT * FROM availability_slots WHERE user_id=? AND date(start_time)=? ORDER BY start_time",
            (user["id"], date_str)
        )).fetchall()]

        free_slots = []
        for slot in slots:
            booked_rows = await db.execute(
                "SELECT proposed_start, proposed_end FROM date_requests WHERE slot_id=? AND status='approved'",
                (slot["id"],)
            )
            booked = [dict(r) for r in await booked_rows.fetchall()]
            free = _free_time_ranges(slot, booked)
            for f_start, f_end in free:
                free_slots.append({"start_time": f_start, "end_time": f_end, "id": slot["id"]})
    finally:
        await db.close()

    return render(request, "partials/_booking_day.html",
                  slots=free_slots, date_str=date_str, token=token,
                  deposit_cents=user.get("deposit_cents", 0))


@router.post("/book/{token}/reserve")
@limiter.limit("5/minute")
async def reserve_slot(request: Request, token: str,
                       date_name: str = Form(...), date_phone: str = Form(...),
                       slot_id: int = Form(...),
                       proposed_start: str = Form(""), proposed_end: str = Form(""),
                       location: str = Form(""), label: str = Form("")):
    date_phone = normalize_phone(date_phone)
    date_name = date_name.strip()

    if not date_name:
        return HTMLResponse('<p class="text-sm text-red-500">Name is required.</p>')
    if len(date_name) > 40:
        return HTMLResponse('<p class="text-sm text-red-500">Name must be 40 characters or fewer.</p>')
    if not date_phone or len(date_phone) != 12 or not date_phone.startswith("+1"):
        return HTMLResponse('<p class="text-sm text-red-500">Enter a valid US phone.</p>')

    db = await get_db()
    try:
        slot = await (await db.execute("SELECT * FROM availability_slots WHERE id=?", (slot_id,))).fetchone()
        if not slot:
            return HTMLResponse('<p class="text-sm text-red-500">Slot not found.</p>')

        slot_date = slot["start_time"][:10]
        prop_start = f"{slot_date}T{proposed_start}" if proposed_start else None
        prop_end = f"{slot_date}T{proposed_end}" if proposed_end else None

        if prop_start and prop_end:
            if prop_end <= prop_start:
                return HTMLResponse('<p class="text-sm text-red-500">End time must be after start time.</p>')
            if prop_start < slot["start_time"] or prop_end > slot["end_time"]:
                return HTMLResponse('<p class="text-sm text-red-500">Selected time must be within the available window.</p>')
            overlap = await db.execute(
                "SELECT id FROM date_requests WHERE slot_id=? AND status='approved' AND proposed_start IS NOT NULL AND proposed_start<? AND proposed_end>?",
                (slot_id, prop_end, prop_start))
            if await overlap.fetchone():
                return HTMLResponse('<p class="text-sm text-red-500">That time is already booked.</p>')

        host = await (await db.execute("SELECT deposit_cents FROM users WHERE id=?", (slot["user_id"],))).fetchone()
        deposit_cents = (host["deposit_cents"] if host else 0) or 0

        cur = await db.execute(
            "INSERT INTO date_requests (slot_id, date_name, date_phone, status, proposed_start, proposed_end, location, label, deposit_cents) VALUES (?,?,?,?,?,?,?,?,?)",
            (slot_id, date_name, date_phone, "pending", prop_start, prop_end, location, label, deposit_cents))
        request_id = cur.lastrowid
        await db.commit()
    finally:
        await db.close()

    if deposit_cents > 0 and settings.STRIPE_SECRET_KEY:
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "CalenDate earnest deposit"},
                        "unit_amount": deposit_cents,
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=f"{settings.BASE_URL}/book/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{settings.BASE_URL}/book/cancel",
                client_reference_id=str(request_id),
            )
            return HTMLResponse(f'<meta http-equiv="refresh" content="0;url={session.url}"><div class="text-center py-8"><div class="text-5xl mb-4">💳</div><h2 class="text-xl font-bold mb-2">Redirecting to Stripe...</h2><p class="text-gray-500">Complete your deposit to send the request.</p></div>')
        except Exception:
            pass

    return HTMLResponse("""<div class='text-center py-8'><div class='text-5xl mb-4'>🎉</div><h2 class='text-xl font-bold mb-2'>Request sent!</h2><p class='text-gray-500'>You'll get a text when it's confirmed.</p></div>""")
