"""Authentication helpers."""

from __future__ import annotations

import re
import secrets
import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def normalize_phone(raw: str) -> str | None:
    """Normalize a US phone number to E.164. Returns None if not a valid US number."""
    digits = re.sub(r'\D', '', raw.strip())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    return None


def generate_token() -> str:
    return secrets.token_urlsafe(8)


async def get_current_user(request) -> dict | None:
    from .db import get_db
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    db = await get_db()
    try:
        row = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = await row.fetchone()
        return dict(user) if user else None
    finally:
        await db.close()
