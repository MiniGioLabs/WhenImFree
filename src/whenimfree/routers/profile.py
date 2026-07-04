"""Profile/settings routes."""

import uuid
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth import get_current_user
from ..db import get_db
from ..utils import render, static_dir, upload_to_s3

router = APIRouter()

ALLOWED_AVATAR_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_AVATAR_BYTES = 5 * 1024 * 1024


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render(request, "settings.html", user=user)


@router.post("/settings/profile")
async def update_profile(request: Request, name: str = Form(...)):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    name = name.strip()
    if not name or len(name) > 40:
        return render(request, "settings.html", user=user, error="Name must be 1–40 characters.")
    db = await get_db()
    try:
        await db.execute("UPDATE users SET name=?, timezone=? WHERE id=?", (name, "US/Eastern", user["id"]))
        await db.commit()
    finally:
        await db.close()
    return RedirectResponse("/settings?saved=1", status_code=302)


@router.post("/settings/avatar", response_class=HTMLResponse)
async def update_avatar(request: Request, avatar: UploadFile = File(...)):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    ext = ALLOWED_AVATAR_TYPES.get(avatar.content_type)
    if not ext:
        return render(request, "settings.html", user=user, error="Please upload a JPG, PNG, or WEBP image.")

    data = await avatar.read()
    if len(data) > MAX_AVATAR_BYTES:
        return render(request, "settings.html", user=user, error="Image must be under 5MB.")

    uid = uuid.uuid4().hex[:8]
    filename = f"{user['id']}-{uid}.{ext}"

    s3_url = upload_to_s3(data, filename, avatar.content_type)
    if s3_url:
        avatar_url = s3_url
    else:
        avatars_dir = static_dir / "avatars"
        avatars_dir.mkdir(parents=True, exist_ok=True)
        (avatars_dir / filename).write_bytes(data)
        avatar_url = f"/static/avatars/{filename}"

    db = await get_db()
    try:
        await db.execute("UPDATE users SET avatar_url=? WHERE id=?", (avatar_url, user["id"]))
        await db.commit()
    finally:
        await db.close()

    return RedirectResponse("/settings?saved=1", status_code=302)
