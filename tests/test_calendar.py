from whenimfree.services.calendar import _restore_cancelled_booking

from conftest import all_slots, insert_slot

# In real usage _split_slot_around_booking shrinks the original slot to exactly
# the booked window (start_time=booked_start, end_time=booked_end) and creates
# separate fragment rows for the before/after portions.  After the date_request
# is deleted, that shrunken slot has no active requests so it lands in the
# overlapping list and triggers the merge.  Every test below inserts it as
# "tok_booked" to mirror that real-world pre-condition.


async def test_left_adjacent_only_merges(db):
    """Available 6-8pm, booked 8-10pm cancelled -> available 6-10pm."""
    await insert_slot(db, 1, "2026-07-04T18:00", "2026-07-04T20:00", "tok1")
    await insert_slot(db, 1, "2026-07-04T20:00", "2026-07-04T22:00", "tok_booked")

    await _restore_cancelled_booking(db, 1, "2026-07-04T20:00", "2026-07-04T22:00")
    await db.commit()

    slots = await all_slots(db, 1)
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-07-04T18:00"
    assert slots[0]["end_time"] == "2026-07-04T22:00"


async def test_right_adjacent_only_merges(db):
    """Booked 8-10pm cancelled, available 10-11pm -> available 8-11pm."""
    await insert_slot(db, 1, "2026-07-04T20:00", "2026-07-04T22:00", "tok_booked")
    await insert_slot(db, 1, "2026-07-04T22:00", "2026-07-04T23:00", "tok1")

    await _restore_cancelled_booking(db, 1, "2026-07-04T20:00", "2026-07-04T22:00")
    await db.commit()

    slots = await all_slots(db, 1)
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-07-04T20:00"
    assert slots[0]["end_time"] == "2026-07-04T23:00"


async def test_both_sides_merge_into_one(db):
    """Available 6-8, booked 8-10 cancelled, available 10-11 -> available 6-11."""
    await insert_slot(db, 1, "2026-07-04T18:00", "2026-07-04T20:00", "tok1")
    await insert_slot(db, 1, "2026-07-04T20:00", "2026-07-04T22:00", "tok_booked")
    await insert_slot(db, 1, "2026-07-04T22:00", "2026-07-04T23:00", "tok2")

    await _restore_cancelled_booking(db, 1, "2026-07-04T20:00", "2026-07-04T22:00")
    await db.commit()

    slots = await all_slots(db, 1)
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-07-04T18:00"
    assert slots[0]["end_time"] == "2026-07-04T23:00"


async def test_no_adjacent_availability_just_restores_the_booking(db):
    """Booked 8-10 cancelled with nothing nearby -> available 8-10."""
    await insert_slot(db, 1, "2026-07-04T20:00", "2026-07-04T22:00", "tok_booked")

    await _restore_cancelled_booking(db, 1, "2026-07-04T20:00", "2026-07-04T22:00")
    await db.commit()

    slots = await all_slots(db, 1)
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-07-04T20:00"
    assert slots[0]["end_time"] == "2026-07-04T22:00"


async def test_overlapping_slot_merges_defensively(db):
    """Available 7-9, cancelled booking 8-10 -> available 7-10."""
    await insert_slot(db, 1, "2026-07-04T19:00", "2026-07-04T21:00", "tok1")
    await insert_slot(db, 1, "2026-07-04T20:00", "2026-07-04T22:00", "tok_booked")

    await _restore_cancelled_booking(db, 1, "2026-07-04T20:00", "2026-07-04T22:00")
    await db.commit()

    slots = await all_slots(db, 1)
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-07-04T19:00"
    assert slots[0]["end_time"] == "2026-07-04T22:00"


async def test_no_duplicate_or_overlapping_rows_left_behind(db):
    """Multiple touching/overlapping slots all collapse into exactly one row."""
    await insert_slot(db, 1, "2026-07-04T18:00", "2026-07-04T20:00", "tok1")
    await insert_slot(db, 1, "2026-07-04T19:30", "2026-07-04T20:30", "tok2")
    await insert_slot(db, 1, "2026-07-04T20:00", "2026-07-04T22:00", "tok_booked")
    await insert_slot(db, 1, "2026-07-04T22:00", "2026-07-04T23:00", "tok3")

    await _restore_cancelled_booking(db, 1, "2026-07-04T20:00", "2026-07-04T22:00")
    await db.commit()

    slots = await all_slots(db, 1)
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-07-04T18:00"
    assert slots[0]["end_time"] == "2026-07-04T23:00"


async def test_unrelated_slots_for_different_host_remain_untouched(db):
    """Cancelling host 1's booking must not touch host 2's slots, even at identical times."""
    await insert_slot(db, 1, "2026-07-04T18:00", "2026-07-04T20:00", "tok1")
    await insert_slot(db, 1, "2026-07-04T20:00", "2026-07-04T22:00", "tok_booked")
    await insert_slot(db, 2, "2026-07-04T18:00", "2026-07-04T22:00", "tok2")

    await _restore_cancelled_booking(db, 1, "2026-07-04T20:00", "2026-07-04T22:00")
    await db.commit()

    host1_slots = await all_slots(db, 1)
    assert len(host1_slots) == 1
    assert host1_slots[0]["start_time"] == "2026-07-04T18:00"
    assert host1_slots[0]["end_time"] == "2026-07-04T22:00"

    host2_slots = await all_slots(db, 2)
    assert len(host2_slots) == 1
    assert host2_slots[0]["start_time"] == "2026-07-04T18:00"
    assert host2_slots[0]["end_time"] == "2026-07-04T22:00"


async def test_unrelated_slot_on_a_different_date_remains_untouched(db):
    """A non-overlapping slot on another date for the same host is left alone."""
    await insert_slot(db, 1, "2026-07-04T20:00", "2026-07-04T22:00", "tok_booked")
    await insert_slot(db, 1, "2026-07-05T18:00", "2026-07-05T20:00", "tok1")

    await _restore_cancelled_booking(db, 1, "2026-07-04T20:00", "2026-07-04T22:00")
    await db.commit()

    slots = await all_slots(db, 1)
    assert len(slots) == 2
    by_start = {s["start_time"]: s["end_time"] for s in slots}
    assert by_start["2026-07-05T18:00"] == "2026-07-05T20:00"
    assert by_start["2026-07-04T20:00"] == "2026-07-04T22:00"
