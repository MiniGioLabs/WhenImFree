import aiosqlite
import pytest_asyncio


@pytest_asyncio.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("""
        CREATE TABLE availability_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            deposit_cents INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    await conn.execute("""
        CREATE TABLE date_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL REFERENCES availability_slots(id),
            status TEXT DEFAULT 'pending',
            proposed_start TEXT,
            proposed_end TEXT
        )
    """)
    await conn.commit()
    try:
        yield conn
    finally:
        await conn.close()


async def insert_slot(db, user_id: int, start: str, end: str, token: str) -> int:
    cur = await db.execute(
        "INSERT INTO availability_slots (user_id, token, start_time, end_time, deposit_cents) VALUES (?,?,?,?,0)",
        (user_id, token, start, end))
    await db.commit()
    return cur.lastrowid


async def all_slots(db, user_id: int) -> list[dict]:
    rows = await db.execute(
        "SELECT * FROM availability_slots WHERE user_id=? ORDER BY start_time", (user_id,))
    return [dict(r) for r in await rows.fetchall()]
