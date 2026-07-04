"""Helpers: templates, formatting."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .config import settings

logger = logging.getLogger(__name__)


def format_slot_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%a %b %d, %I:%M %p")
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


_DOW_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def format_dows(dows_str: str) -> str:
    try:
        return ", ".join(_DOW_NAMES[int(d)] for d in str(dows_str).split(",") if d.strip().isdigit())
    except (ValueError, IndexError):
        return str(dows_str)


def format_hhmm(hhmm: str) -> str:
    try:
        h, m = int(hhmm[:2]), int(hhmm[3:5])
        ap = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {ap}" if m else f"{h12} {ap}"
    except (ValueError, TypeError, IndexError):
        return hhmm


def format_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('1'):
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone


_tdir = Path(settings.TEMPLATES_DIR) if settings.TEMPLATES_DIR else Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_tdir))
static_dir = Path(settings.STATIC_DIR) if settings.STATIC_DIR else Path(__file__).parent / "static"
templates.env.globals["format_slot_time"] = format_slot_time
templates.env.globals["format_slot_day"] = format_slot_day
templates.env.globals["format_time"] = format_time
templates.env.globals["format_dows"] = format_dows
templates.env.globals["format_hhmm"] = format_hhmm
templates.env.globals["format_phone"] = format_phone


def render(request: Request, template: str, **kwargs) -> HTMLResponse:
    return templates.TemplateResponse(request, template, {"request": request, **kwargs})


def upload_to_s3(file_data: bytes, filename: str, content_type: str) -> str:
    """Upload a file to S3. Returns the public URL, or empty string if not configured."""
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
