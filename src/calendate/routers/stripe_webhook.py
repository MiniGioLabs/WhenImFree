"""Stripe webhook handler for earnest deposits."""

import logging
import stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import settings
from ..db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe checkout.session.completed — mark deposit as paid."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return JSONResponse({"error": "Invalid signature"}, status_code=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        request_id = session.get("client_reference_id")
        if request_id:
            db = await get_db()
            try:
                await db.execute(
                    "UPDATE date_requests SET stripe_session_id=?, deposit_paid_cents=? WHERE id=?",
                    (session["id"], session.get("amount_total", 0), int(request_id)),
                )
                await db.commit()
                logger.info("Deposit paid for request %s: %s cents", request_id, session.get("amount_total"))
            finally:
                await db.close()

    return JSONResponse({"status": "ok"})
