import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from database import crud
from database.models import BachsCheckout, User
from providers.telnyx_provider import TelnyxProvider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bachs_payments"])

BACHS_API_KEY = os.getenv("BACHS_API_KEY", "")
BACHS_WEBHOOK_SECRET = os.getenv("BACHS_WEBHOOK_SECRET", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")

# Sandbox keys talk to the sandbox API, live keys to production
BACHS_API_BASE = os.getenv("BACHS_API_BASE") or (
    "https://sandbox-api.bachs.io" if BACHS_API_KEY.startswith("sk_sandbox_") else "https://api.bachs.io"
)

SIGNATURE_TOLERANCE_SECONDS = 300

# Prices live here, never trusted from the browser. Keep in sync with the website's plans.
NUMBER_PRICES = {1: Decimal("3.99"), 3: Decimal("9.99"), 6: Decimal("17.99"), 12: Decimal("29.99")}
CREDIT_PRICES = {20: Decimal("2.49"), 50: Decimal("5.49"), 100: Decimal("9.99")}
COUNTRIES = {"US", "CA"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateCheckoutRequest(BaseModel):
    purpose: str = Field(default="number", description="'number' or 'credits'")
    user_email: Optional[str] = None
    success_url: str
    cancel_url: str
    # purpose == "number"
    country: Optional[str] = None
    duration_months: Optional[int] = None
    refund_policy_accepted: Optional[bool] = None
    refund_policy_version: Optional[str] = None
    refund_policy_accepted_at: Optional[str] = None
    service_ends_on: Optional[str] = None
    # purpose == "credits"
    number_id: Optional[str] = None
    sms_credits: Optional[int] = None
    # Sent by the website for display only; the server price is what gets charged
    amount: Optional[str] = None
    currency: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_signature(raw_body: bytes, headers) -> bool:
    """Check X-Bachs-Signature-V2 ("t=...,v1=...") against HMAC-SHA256 of "{t}.{raw_body}"."""
    if not BACHS_WEBHOOK_SECRET:
        return False

    header = headers.get("x-bachs-signature-v2")
    if header:
        fields = [part.strip().split("=", 1) for part in header.split(",") if "=" in part]
        timestamp = next((v for k, v in fields if k == "t"), None)
        signatures = [v for k, v in fields if k == "v1"]
    else:
        timestamp = headers.get("x-bachs-timestamp")
        signatures = [headers.get("x-bachs-signature", "")]

    try:
        if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
            return False
    except (TypeError, ValueError):
        return False

    expected = hmac.new(
        BACHS_WEBHOOK_SECRET.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures if sig)


async def _find_and_purchase_number(country: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Search for and purchase a number via Telnyx.
    Returns (purchase_result_dict, provider_name) or (None, None) on failure.
    """
    telnyx = TelnyxProvider()

    numbers = await telnyx.search_numbers(country)
    if numbers:
        result = await telnyx.purchase_number(numbers[0]["phone_number"])
        if result.get("status") in ("active", "mock", "pending"):
            return result, "telnyx"

    return None, None


async def _configure_webhook(provider: str, number_sid: str) -> bool:
    if not WEBHOOK_BASE_URL:
        return True
    webhook_url = f"{WEBHOOK_BASE_URL}/webhooks/telnyx"
    return await TelnyxProvider().configure_webhook(number_sid, webhook_url)


async def _fulfil(db: AsyncSession, order: BachsCheckout) -> None:
    """Deliver what was paid for. Raises on failure so the webhook is retried."""
    user = await crud.get_user_by_email(db, order.user_email)
    if not user:
        user = await crud.create_web_user(db, email=order.user_email)
        logger.info(f"Created web user {user.id} for email {order.user_email} via Bachs webhook")

    if order.purpose == "credits":
        await crud.add_sms_credits(db, user_id=user.id, number_id=order.number_id, amount=order.sms_credits)
        logger.info(f"Added {order.sms_credits} credits to number {order.number_id} for user {user.id}")
    else:
        purchase_result, provider = await _find_and_purchase_number(order.country.lower())
        if not purchase_result:
            raise RuntimeError(f"number purchase failed for country {order.country}")

        number = await crud.create_number(
            db,
            user_id=user.id,
            phone_number=purchase_result["phone_number"],
            number_sid=purchase_result.get("sid", ""),
            provider=provider or "unknown",
            country=order.country,
            duration_months=order.duration_months,
        )
        if purchase_result.get("sid"):
            await _configure_webhook(provider or "telnyx", purchase_result["sid"])

        # Create initial 15 SMS credits
        await crud.get_or_create_sms_credit(db, user_id=user.id, number_id=number.id, initial=15)
        logger.info(f"Provisioned number {number.phone_number} for user {user.id}")

    await crud.create_transaction(
        db,
        user_id=user.id,
        amount_ngn=float(order.amount),
        tx_type="number_purchase" if order.purpose == "number" else "credit_topup",
        status="completed",
    )


# ---------------------------------------------------------------------------
# 1. POST /payments/bachs/create-checkout
# ---------------------------------------------------------------------------

@router.post("/payments/bachs/create-checkout")
async def create_checkout(req: CreateCheckoutRequest, db: AsyncSession = Depends(get_db)):
    if not BACHS_API_KEY:
        raise HTTPException(status_code=500, detail="Bachs API key not configured")

    order = BachsCheckout(purpose=req.purpose, currency="USD")
    metadata = {"purpose": req.purpose}

    if req.purpose == "number":
        country = (req.country or "").upper()
        if country not in COUNTRIES or req.duration_months not in NUMBER_PRICES:
            raise HTTPException(status_code=400, detail="Unknown country or plan")
        if not req.user_email:
            raise HTTPException(status_code=400, detail="user_email is required")
        if not req.refund_policy_accepted:
            raise HTTPException(status_code=400, detail="The no-refund policy must be accepted")
        order.user_email = req.user_email.lower().strip()
        order.country = country
        order.duration_months = req.duration_months
        order.amount = NUMBER_PRICES[req.duration_months]
        metadata.update({
            "country": country,
            "duration_months": str(req.duration_months),
            "refund_policy_accepted": "true",
            "refund_policy_version": req.refund_policy_version or "",
            "refund_policy_accepted_at": req.refund_policy_accepted_at or "",
            "service_ends_on": req.service_ends_on or "",
        })
    elif req.purpose == "credits":
        if req.sms_credits not in CREDIT_PRICES:
            raise HTTPException(status_code=400, detail="Unknown credit package")
        try:
            number_id = uuid.UUID(req.number_id or "")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid number_id")
        number = await crud.get_number_by_id(db, number_id)
        if not number:
            raise HTTPException(status_code=404, detail="Number not found")
        owner = (await db.execute(select(User).where(User.id == number.user_id))).scalar_one()
        if req.user_email and owner.email and owner.email != req.user_email.lower().strip():
            raise HTTPException(status_code=403, detail="That number belongs to another account")
        if not owner.email:
            raise HTTPException(status_code=400, detail="That number has no email on file")
        order.user_email = owner.email
        order.number_id = number_id
        order.sms_credits = req.sms_credits
        order.amount = CREDIT_PRICES[req.sms_credits]
        metadata.update({"number_id": str(number_id), "sms_credits": str(req.sms_credits)})
    else:
        raise HTTPException(status_code=400, detail="purpose must be 'number' or 'credits'")

    order.id = uuid.uuid4()
    metadata["order_id"] = str(order.id)
    order.metadata_json = json.dumps(metadata)

    payload = {
        "pricing": {"currency": "USD", "amount": f"{order.amount:.2f}"},
        "customer": {"email": order.user_email},
        "success_url": req.success_url,
        "cancel_url": req.cancel_url,
        "reference": str(order.id),
        "metadata": metadata,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{BACHS_API_BASE}/v1/checkout-sessions",
                headers={"Authorization": f"Bearer {BACHS_API_KEY}"},
                json=payload,
            )
    except httpx.HTTPError as e:
        logger.error(f"Bachs create-checkout network error: {e}")
        raise HTTPException(status_code=502, detail="Payment provider unavailable, please try again")

    if response.status_code >= 400:
        logger.error(f"Bachs create-checkout error {response.status_code}: {response.text}")
        raise HTTPException(status_code=502, detail="Could not start checkout, please try again")

    session = response.json()
    order.checkout_id = session.get("checkout_id")
    db.add(order)
    await db.commit()

    return {"checkout_url": session.get("checkout_url"), "checkout_id": order.checkout_id}


# ---------------------------------------------------------------------------
# 2. POST /payments/bachs/webhook
# ---------------------------------------------------------------------------

@router.post("/payments/bachs/webhook")
async def bachs_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw_body = await request.body()
    if not _verify_signature(raw_body, request.headers):
        logger.warning("Bachs webhook rejected: bad or missing signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(raw_body)
    event_type = event.get("type")
    data = event.get("data") or {}

    # Fulfil on whichever of these arrives first; the status claim below makes it happen once
    if event_type == "checkout.completed":
        if data.get("payment_status") != "paid":
            return {"status": "ignored", "reason": "not paid"}
    elif event_type != "collection.succeeded":
        return {"status": "ignored", "event": event_type}

    checkout_id = data.get("checkout_id")
    if not checkout_id:
        return {"status": "ignored", "reason": "no checkout_id"}

    result = await db.execute(select(BachsCheckout).where(BachsCheckout.checkout_id == checkout_id))
    order = result.scalar_one_or_none()
    if not order:
        logger.error(f"Bachs webhook for unknown checkout {checkout_id}")
        return {"status": "ignored", "reason": "unknown checkout"}

    try:
        paid = Decimal(str(data.get("amount", "0")))
    except InvalidOperation:
        paid = Decimal("0")
    if paid < order.amount:
        logger.error(f"Bachs checkout {checkout_id} paid {paid}, expected {order.amount}; not fulfilling")
        return {"status": "error", "detail": "amount mismatch"}

    # Atomically claim the order so retries and the second event type do nothing
    claim = await db.execute(
        update(BachsCheckout)
        .where(BachsCheckout.id == order.id, BachsCheckout.status == "pending")
        .values(status="processing")
    )
    await db.commit()
    if claim.rowcount == 0:
        return {"status": "ok", "detail": "already handled"}

    try:
        await _fulfil(db, order)
    except Exception as e:
        # Put it back so Bachs's retry can try again
        logger.exception(f"Fulfilment failed for Bachs checkout {checkout_id}: {e}")
        await db.rollback()
        await db.execute(update(BachsCheckout).where(BachsCheckout.id == order.id).values(status="pending"))
        await db.commit()
        raise HTTPException(status_code=500, detail="Fulfilment failed")

    await db.execute(
        update(BachsCheckout)
        .where(BachsCheckout.id == order.id)
        .values(status="fulfilled", fulfilled_at=datetime.utcnow())
    )
    await db.commit()
    return {"status": "ok", "item": order.purpose}
