"""Calendar building + recurring slot expansion."""


def _expand_recurring(recurring: list, year: int, month: int) -> list:
    """Expand recurring slot rules into concrete slot dicts for every matching day in a month."""
    import calendar as cal_mod
    from datetime import date

    result = []
    _, days_in_month = cal_mod.monthrange(year, month)

    for day_num in range(1, days_in_month + 1):
        d = date(year, month, day_num)
        # isoweekday: Mon=1..Sun=7 → we want Sun=0, Mon=1..Sat=6
        dow = d.isoweekday() % 7
        for r in recurring:
            if not r.get("active", 1):
                continue
            rule_dows = {int(x) for x in str(r["dows"]).split(",") if x.strip().isdigit()}
            if dow in rule_dows:
                ds = d.isoformat()
                result.append({
                    "id": None,
                    "start_time": f"{ds}T{r['start_hhmm']}",
                    "end_time": f"{ds}T{r['end_hhmm']}",
                    "recurring": True,
                    "recurring_id": r["id"],
                    "label": r.get("label") or "",
                    "booked": False,
                })
    return result


def _build_calendar(
    year: int,
    month: int,
    slots: list,
    recurring: list = None,
    bookings: list = None,
    blocked_times: set = None,
) -> list:
    """
    Build a weekly grid for the given month.
    - slots: one-off availability slots (already filtered to available status)
    - recurring: recurring slot rules (expanded per-month; occurrences that overlap any
                 entry in blocked_times are suppressed)
    - bookings: accepted booking_requests to render as green "booked" entries (host calendar only)
    - blocked_times: set of (start_time, end_time) tuples from accepted bookings; any recurring
                     occurrence whose window overlaps a blocked range is hidden (supports partial
                     booking where a sub-range of a recurring window was accepted)
    """
    import calendar as cal_mod
    from datetime import date

    today = date.today()
    cal = cal_mod.Calendar(cal_mod.SUNDAY)

    by_date: dict = {}
    for s in slots:
        ds = s["start_time"][:10]
        by_date.setdefault(ds, []).append({**s, "recurring": False, "booked": False})

    if recurring:
        for s in _expand_recurring(recurring, year, month):
            if blocked_times:
                occ_start = s["start_time"]
                occ_end = s["end_time"]
                # Block this occurrence if any accepted booking overlaps with it
                # (handles partial bookings where requested_start/end != occurrence bounds)
                if any(b_start < occ_end and b_end > occ_start for b_start, b_end in blocked_times):
                    continue
            ds = s["start_time"][:10]
            by_date.setdefault(ds, []).append(s)

    if bookings:
        for b in bookings:
            ds = b["requested_start"][:10]
            by_date.setdefault(ds, []).append({
                "id": b["id"],
                "start_time": b["requested_start"],
                "end_time": b["requested_end"],
                "recurring": False,
                "booked": True,
                "label": b.get("guest_name", "Booked"),
                "guest_phone": b.get("guest_phone", ""),
                "note": b.get("note", ""),
            })

    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_days = []
        for day_num in week:
            if day_num == 0:
                week_days.append({"day": "", "date_str": "", "slots": [], "is_today": False, "is_other_month": True})
            else:
                ds = f"{year}-{month:02d}-{day_num:02d}"
                day_slots = sorted(by_date.get(ds, []), key=lambda x: x["start_time"])
                week_days.append({"day": day_num, "date_str": ds, "slots": day_slots,
                                  "is_today": ds == today.isoformat(), "is_other_month": False,
                                  "is_past": date(year, month, day_num) < today})
        weeks.append(week_days)
    return weeks
