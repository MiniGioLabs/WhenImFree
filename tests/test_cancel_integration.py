import pytest

from whenimfree.services.calendar import _restore_cancelled_booking

from conftest import all_slots, insert_slot


async def cancel(db, request_id: int, user_id: int, start: str, end: str) -> None:
    """Mirrors the operation order in routers.requests.cancel_request."""
    try:
        await db.execute("DELETE FROM date_requests WHERE id=?", (request_id,))
        await _restore_cancelled_booking(db, user_id, start, end)
    except Exception:
        await db.rollback()
        raise
    await db.commit()


async def test_cancel_deletes_request_before_restoring_its_own_slot(db):
    """The approved request's slot_id is exactly the booked window, so restoring
    availability deletes that very row. The request must be deleted first or this
    raises a foreign key violation (slot_id is FK-referenced by date_requests).
    """
    slot_id = await insert_slot(db, 1, "2026-07-10T20:00", "2026-07-10T22:00", "midtok")
    cur = await db.execute(
        "INSERT INTO date_requests (slot_id, status, proposed_start, proposed_end) VALUES (?,?,?,?)",
        (slot_id, "approved", "2026-07-10T20:00", "2026-07-10T22:00"))
    await db.commit()
    request_id = cur.lastrowid

    await cancel(db, request_id, 1, "2026-07-10T20:00", "2026-07-10T22:00")

    slots = await all_slots(db, 1)
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-07-10T20:00"
    assert slots[0]["end_time"] == "2026-07-10T22:00"

    remaining = await (await db.execute("SELECT id FROM date_requests WHERE id=?", (request_id,))).fetchone()
    assert remaining is None


async def test_cancel_is_transactional_on_failure(db):
    """If restoration fails partway, the request deletion must roll back too."""
    slot_id = await insert_slot(db, 1, "2026-07-10T18:00", "2026-07-10T20:00", "tok1")
    cur = await db.execute(
        "INSERT INTO date_requests (slot_id, status, proposed_start, proposed_end) VALUES (?,?,?,?)",
        (slot_id, "approved", "2026-07-10T18:00", "2026-07-10T20:00"))
    await db.commit()
    request_id = cur.lastrowid

    with pytest.raises(RuntimeError):
        try:
            await db.execute("DELETE FROM date_requests WHERE id=?", (request_id,))
            raise RuntimeError("simulated failure during restoration")
        except Exception:
            await db.rollback()
            raise

    remaining = await (await db.execute("SELECT id FROM date_requests WHERE id=?", (request_id,))).fetchone()
    assert remaining is not None

    slots = await all_slots(db, 1)
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-07-10T18:00"
