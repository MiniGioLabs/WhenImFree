"""Auth routes."""

import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth import hash_password, verify_password, get_current_user, normalize_phone
from ..db import get_db
from ..limiter import limiter
from ..utils import render

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
    return render(request, "login.html")


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, phone: str = Form(...), password: str = Form(...)):
    if len(password) < 6 or len(password) > 20:
        return render(request, "login.html", error="Invalid phone or password.")
    normalized = normalize_phone(phone)
    if not normalized:
        return render(request, "login.html", error="Invalid phone or password.")
    db = await get_db()
    try:
        row = await db.execute("SELECT * FROM users WHERE phone = ?", (normalized,))
        user = await row.fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return render(request, "login.html", error="Invalid phone or password.")
        request.session["user_id"] = user["id"]
        return RedirectResponse("/dashboard", status_code=303)
    finally:
        await db.close()


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
    return render(request, "signup.html")


@router.get("/signin", response_class=HTMLResponse)
async def signin_redirect(request: Request):
    return RedirectResponse("/login", status_code=301)


@router.post("/signup")
@limiter.limit("5/minute")
async def signup(
    request: Request,
    username: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
):
    username = username.strip().lower()
    name = name.strip()
    normalized_phone = normalize_phone(phone)

    if not re.match(r"^[a-z0-9_]{3,20}$", username):
        return render(request, "signup.html", error="Username must be 3–20 characters: letters, numbers, underscores only.")
    if not normalized_phone:
        return render(request, "signup.html", error="Enter a valid US phone number (10 digits).")
    if not name or len(name) > 40:
        return render(request, "signup.html", error="Name must be 1–40 characters.")
    if len(password) < 6:
        return render(request, "signup.html", error="Password must be at least 6 characters.")
    if len(password) > 20:
        return render(request, "signup.html", error="Password must be 20 characters or fewer.")
    if not re.search(r"[A-Z]", password):
        return render(request, "signup.html", error="Password must contain an uppercase letter.")
    if not re.search(r"[a-z]", password):
        return render(request, "signup.html", error="Password must contain a lowercase letter.")
    if not re.search(r"[0-9]", password):
        return render(request, "signup.html", error="Password must contain a number.")

    db = await get_db()
    try:
        existing = await (await db.execute("SELECT id FROM users WHERE username = ?", (username,))).fetchone()
        if existing:
            return render(request, "signup.html", error="That username is taken — try another.")
        existing_phone = await (await db.execute("SELECT id FROM users WHERE phone = ?", (normalized_phone,))).fetchone()
        if existing_phone:
            return render(request, "signup.html", error="An account with that phone number already exists.")

        cursor = await db.execute(
            "INSERT INTO users (username, phone, password_hash, name) VALUES (?, ?, ?, ?)",
            (username, normalized_phone, hash_password(password), name),
        )
        await db.commit()
        request.session["user_id"] = cursor.lastrowid
        return RedirectResponse("/dashboard", status_code=303)
    finally:
        await db.close()


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
