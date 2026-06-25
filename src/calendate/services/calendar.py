"""Calendar building + slot splitting/merging."""


def _build_calendar(year: int, month: int, slots: list, booked: list, approved_requests: list = None) -> list:
    import calendar as cal_mod
    from datetime import date

    today = date.today()
    cal = cal_mod.Calendar(cal_mod.SUNDAY)

    slot_request_map = {}
    if approved_requests:
        for req in approved_requests:
            slot_request_map[req["slot_id"]] = req["id"]

    by_date = {}
    for s in slots:
        ds = s["start_time"][:10]
        by_date.setdefault(ds, []).append(s)

    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_days = []
        for day_num in week:
            if day_num == 0:
                week_days.append({"day": "", "date_str": "", "slots": [], "is_today": False, "is_other_month": True})
            else:
                ds = f"{year}-{month:02d}-{day_num:02d}"
                day_slots = by_date.get(ds, [])
                slot_list = []
                for s in day_slots:
                    request_id = slot_request_map.get(s["id"])
                    slot_list.append({
                        "id": s["id"], "start_time": s["start_time"], "end_time": s["end_time"],
                        "status": "booked" if request_id else "open",
                        "request_id": request_id,
                    })
                week_days.append({"day": day_num, "date_str": ds, "slots": slot_list,
                                  "is_today": ds == today.isoformat(), "is_other_month": False})
        weeks.append(week_days)
    return weeks


def _build_booking_calendar(slots: list, booked_by_slot: dict | None = None, year: int = None, month: int = None) -> dict:
    import calendar as cal_mod
    from datetime import date

    today = date.today()
    if year is None: year = today.year
    if month is None: month = today.month
    booked_by_slot = booked_by_slot or {}

    cal = cal_mod.Calendar(cal_mod.SUNDAY)
    open_dates = set()
    for s in slots:
        if _free_time_ranges(s, booked_by_slot.get(s["id"], [])):
            open_dates.add(s["start_time"][:10])

    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_days = []
        for day_num in week:
            if day_num == 0:
                week_days.append({"day": "", "date_str": "", "is_open": False, "is_today": False, "is_other_month": True})
            else:
                ds = f"{year}-{month:02d}-{day_num:02d}"
                week_days.append({"day": day_num, "date_str": ds, "is_open": ds in open_dates,
                                  "is_today": ds == today.isoformat(), "is_other_month": False})
        weeks.append(week_days)
    return {"year": year, "month": month, "weeks": weeks}


def _free_time_ranges(slot: dict, booked: list[dict]) -> list:
    from datetime import datetime

    slot_start = datetime.fromisoformat(slot["start_time"])
    slot_end = datetime.fromisoformat(slot["end_time"])

    booked_intervals = []
    for req in booked:
        b_start = req.get("proposed_start")
        b_end = req.get("proposed_end")
        if b_start and b_end:
            booked_intervals.append((datetime.fromisoformat(b_start), datetime.fromisoformat(b_end)))

    booked_intervals.sort()
    merged = []
    for start, end in booked_intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    free = []
    cursor = slot_start
    for b_start, b_end in merged:
        if cursor < b_start:
            free.append((cursor.isoformat(), b_start.isoformat()))
        cursor = max(cursor, b_end)
    if cursor < slot_end:
        free.append((cursor.isoformat(), slot_end.isoformat()))
    return free


async def _split_slot_around_booking(db, slot_id: int, booked_start: str, booked_end: str) -> None:
    from ..auth import generate_token

    row = await db.execute("SELECT * FROM availability_slots WHERE id=?", (slot_id,))
    slot = await row.fetchone()
    if not slot: return

    if booked_start > slot["start_time"]:
        await db.execute(
            "INSERT INTO availability_slots (user_id, token, start_time, end_time, deposit_cents) VALUES (?,?,?,?,0)",
            (slot["user_id"], generate_token(), slot["start_time"], booked_start))
    if booked_end < slot["end_time"]:
        await db.execute(
            "INSERT INTO availability_slots (user_id, token, start_time, end_time, deposit_cents) VALUES (?,?,?,?,0)",
            (slot["user_id"], generate_token(), booked_end, slot["end_time"]))

    # Shrink the original slot to exactly the booked window so its leftover time isn't
    # double-counted alongside the new fragment rows above (date_requests.slot_id keeps
    # pointing at this row, so it can't simply be deleted).
    await db.execute(
        "UPDATE availability_slots SET start_time=?, end_time=? WHERE id=?",
        (booked_start, booked_end, slot_id))


async def _restore_cancelled_booking(db, user_id: int, start: str, end: str) -> None:
    """Reopen a cancelled booking's time range as availability for this host, merging it
    with any availability slots that are adjacent to or overlap that range so we don't
    leave duplicate or overlapping rows behind.
    """
    from ..auth import generate_token

    rows = await db.execute(
        "SELECT * FROM availability_slots WHERE user_id=? AND end_time>=? AND start_time<=?",
        (user_id, start, end))
    overlapping = [dict(r) for r in await rows.fetchall()]

    merged_start = min([start] + [s["start_time"] for s in overlapping])
    merged_end = max([end] + [s["end_time"] for s in overlapping])

    for s in overlapping:
        await db.execute("DELETE FROM availability_slots WHERE id=?", (s["id"],))

    await db.execute(
        "INSERT INTO availability_slots (user_id, token, start_time, end_time, deposit_cents) VALUES (?,?,?,?,0)",
        (user_id, generate_token(), merged_start, merged_end))
