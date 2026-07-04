"""Database — SQLite with aiosqlite."""

from __future__ import annotations

import aiosqlite
import logging
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)
_db_path: str | None = None


def _get_db_path() -> str:
    global _db_path
    if _db_path is None:
        _db_path = settings.DATABASE_PATH or str(Path(__file__).parent.parent.parent / "whenimfree.db")
    return _db_path


async def get_db() -> aiosqlite.Connection:
    """Create a fresh connection per request."""
    db = await aiosqlite.connect(_get_db_path())
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS recurring_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                dows TEXT NOT NULL,
                start_hhmm TEXT NOT NULL,
                end_hhmm TEXT NOT NULL,
                label TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                timezone TEXT DEFAULT 'US/Eastern',
                avatar_url TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS booking_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                guest_name TEXT NOT NULL,
                guest_phone TEXT NOT NULL,
                requested_start TEXT NOT NULL,
                requested_end TEXT NOT NULL,
                note TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS availability_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)

        await db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_slots_user_id ON availability_slots(user_id);
            CREATE INDEX IF NOT EXISTS idx_slots_start ON availability_slots(start_time);
            CREATE INDEX IF NOT EXISTS idx_recurring_user ON recurring_slots(user_id);
            CREATE INDEX IF NOT EXISTS idx_requests_owner ON booking_requests(slot_owner_id);
        """)

        # Migrate: add status column to availability_slots if missing
        try:
            await db.execute("ALTER TABLE availability_slots ADD COLUMN status TEXT DEFAULT 'available'")
            await db.commit()
        except Exception:
            pass

        await db.commit()
        logger.info("Database initialized")
    finally:
        await db.close()
