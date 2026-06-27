"""Helpers: templates, formatting, SMS."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from twilio.rest import Client as TwilioClient

from .config import settings

logger = logging.getLogger(__name__)
_twilio: TwilioClient | None = None


def get_twilio() -> TwilioClient:
    global _twilio
    if _twilio is None and settings.TWILIO_ACCOUNT_SID:
        _twilio = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _twilio


async def send_sms(to: str, body: str) -> bool:
    if not settings.twilio_configured:
        logger.info("[SMS] To: %s — %s", to, body[:80])
        return True
    try:
        msg = get_twilio().messages.create(body=body, from_=settings.TWILIO_PHONE_NUMBER, to=to)
        logger.info("SMS sent: %s", msg.sid)
        return True
    except Exception as e:
        logger.error("SMS failed: %s", e)
        return False


def format_slot_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%a %b %d, %I:%M %p") + " EST"
    except (ValueError, TypeError):
        return iso


def format_slot_day(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%a %b %d")
    except (ValueError, TypeError):
        return iso[:10]


def format_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return iso[11:16]


def sort_by_start(reqs: list[dict]) -> list[dict]:
    """Chronological order by the actual booked window (proposed_start if a sub-range was requested)."""
    return sorted(reqs, key=lambda r: r.get("proposed_start") or r.get("start_time") or "")


# ── Templates ──────────────────────────────────────────────────────

_tdir = Path(settings.TEMPLATES_DIR) if settings.TEMPLATES_DIR else Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_tdir))
static_dir = Path(settings.STATIC_DIR) if settings.STATIC_DIR else Path(__file__).parent / "static"
templates.env.globals["format_slot_time"] = format_slot_time
templates.env.globals["format_slot_day"] = format_slot_day
templates.env.globals["format_time"] = format_time
templates.env.filters["sort_by_start"] = sort_by_start


def render(request: Request, template: str, **kwargs) -> HTMLResponse:
    return templates.TemplateResponse(request, template, {"request": request, **kwargs})


def upload_to_s3(file_data: bytes, filename: str, content_type: str) -> str:
    """Upload a file to S3. Returns the public URL, or empty string if not configured."""
    from .config import settings
    if not settings.s3_configured:
        return ""
    import boto3
    client = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    client.put_object(
        Bucket=settings.AWS_S3_BUCKET,
        Key=f"avatars/{filename}",
        Body=file_data,
        ContentType=content_type,
        ACL="public-read",
    )
    return f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/avatars/{filename}"
