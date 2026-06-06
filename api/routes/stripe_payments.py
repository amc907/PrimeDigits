import os
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from database import crud
from providers.telnyx_provider import TelnyxProvider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stripe_payments"])

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")

stripe.api_key = STRIPE_SECRET_KEY


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateIntentRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount in cents (e.g. 399 for $3.99)")
    currency: str = Field(default="usd")
    country: str = Field(..., description="Country code: us, ca")
    duration_months: int = Field(default=1, ge=1, le=12)
    user_email: str
    item_type: str = Field(default="number", description="'number' or 'credits'")
    number_id: Optional[str] = Field(default=None, description="Required when item_type='credits'")
    credit_amount: Optional[int] = Field(default=None, description="Required when item_type='credits'")


class RegisterWebUserRequest(BaseModel):
    email: str
    full_name: Optional[str] = None
    supabase_id: str


class VerifyWebUserRequest(BaseModel):
    supabase_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _stripe_call(func, *args, **kwargs):
    """Run a synchronous Stripe SDK call in the default executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


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


# ---------------------------------------------------------------------------
# 1. POST /payments/stripe/create-intent
# ---------------------------------------------------------------------------

@router.post("/payments/stripe/create-intent")
async def create_payment_intent(
    req: CreateIntentRequest,
    db: AsyncSession = Depends(get_db)
):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe secret key not configured")

    metadata = {
        "country": req.country,
        "duration_months": str(req.duration_months),
        "user_email": req.user_email.lower().strip(),
        "item_type": req.item_type,
    }
    if req.item_type == "credits":
        metadata["number_id"] = req.number_id or ""
        metadata["credit_amount"] = str(req.credit_amount or 0)

    try:
        intent = await _stripe_call(
            stripe.PaymentIntent.create,
            amount=req.amount,
            currency=req.currency.lower(),
            automatic_payment_methods={"enabled": True},
            metadata=metadata,
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe create-intent error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
    }


# ---------------------------------------------------------------------------
# 2. POST /payments/stripe/webhook
# ---------------------------------------------------------------------------

@router.post("/payments/stripe/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        if STRIPE_WEBHOOK_SECRET and sig_header:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            event = json.loads(payload)
            if not isinstance(event, dict):
                raise ValueError("Invalid payload")
    except Exception as e:
        logger.warning(f"Stripe webhook signature/payload error: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_type = event.get("type")
    if event_type != "payment_intent.succeeded":
        return {"status": "ignored", "event": event_type}

    payment_intent = event.get("data", {}).get("object", {})
    metadata = payment_intent.get("metadata", {})
    email = metadata.get("user_email", "").lower().strip()
    item_type = metadata.get("item_type", "number")
    amount_cents = payment_intent.get("amount", 0)
    amount_dollars = round(amount_cents / 100, 2)
    pi_id = payment_intent.get("id")

    if not email:
        logger.error("Webhook missing user_email in metadata")
        return {"status": "error", "detail": "missing email"}

    # Find or create user by email
    user = await crud.get_user_by_email(db, email)
    if not user:
        user = await crud.create_web_user(db, email=email)
        logger.info(f"Created web user {user.id} for email {email} via Stripe webhook")

    # Log transaction as completed
    tx_type = "number_purchase" if item_type == "number" else "credit_topup"
    await crud.create_transaction(
        db,
        user_id=user.id,
        amount_ngn=amount_dollars,
        tx_type=tx_type,
        stripe_payment_intent_id=pi_id,
        status="completed"
    )

    if item_type == "credits":
        number_id_str = metadata.get("number_id")
        credit_amount_str = metadata.get("credit_amount", "0")
        if not number_id_str:
            logger.error(f"Credit purchase webhook missing number_id for user {user.id}")
            return {"status": "error", "detail": "missing number_id for credit purchase"}
        try:
            number_id = uuid.UUID(number_id_str)
        except ValueError:
            logger.error(f"Invalid number_id UUID: {number_id_str}")
            return {"status": "error", "detail": "invalid number_id"}

        try:
            credit_amount = int(credit_amount_str)
        except ValueError:
            credit_amount = 0

        await crud.add_sms_credits(db, user_id=user.id, number_id=number_id, amount=credit_amount)
        logger.info(f"Added {credit_amount} credits to number {number_id} for user {user.id}")
        return {"status": "ok", "item": "credits"}

    # item_type == "number"
    country = metadata.get("country", "us")
    duration_months_str = metadata.get("duration_months", "1")
    try:
        duration_months = int(duration_months_str)
    except ValueError:
        duration_months = 1

    purchase_result, provider = await _find_and_purchase_number(country)
    if not purchase_result:
        logger.error(f"Failed to purchase number for user {user.id}, country {country}")
        return {"status": "error", "detail": "number purchase failed"}

    number = await crud.create_number(
        db,
        user_id=user.id,
        phone_number=purchase_result["phone_number"],
        number_sid=purchase_result.get("sid", ""),
        provider=provider or "unknown",
        country=country.upper(),
        duration_months=duration_months,
    )

    # Configure webhook for the number
    if purchase_result.get("sid"):
        await _configure_webhook(provider or "telnyx", purchase_result["sid"])

    # Create initial 15 SMS credits
    await crud.get_or_create_sms_credit(db, user_id=user.id, number_id=number.id, initial=15)
    logger.info(f"Provisioned number {number.phone_number} for user {user.id}")

    return {"status": "ok", "item": "number", "number_id": str(number.id)}


# ---------------------------------------------------------------------------
# 3. GET /payments/stripe/history/{email}
# ---------------------------------------------------------------------------

@router.get("/payments/stripe/history/{email}")
async def get_stripe_payment_history(email: str, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_email(db, email)
    if not user:
        return {"transactions": []}

    transactions = await crud.get_transactions_for_user(db, user.id)
    return {
        "transactions": [
            {
                "id": str(tx.id),
                "amount": float(tx.amount_ngn),
                "type": tx.type,
                "status": tx.status,
                "stripe_payment_intent_id": tx.stripe_payment_intent_id,
                "flutterwave_ref": tx.flutterwave_ref,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
            for tx in transactions
        ]
    }


# ---------------------------------------------------------------------------
# 4. GET /numbers/web/{email}
# ---------------------------------------------------------------------------

@router.get("/numbers/web/{email}")
async def get_web_user_numbers(email: str, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_email(db, email)
    if not user:
        return {"numbers": []}

    numbers = await crud.get_active_numbers_for_user(db, user.id)
    result = []
    for num in numbers:
        credit = await crud.get_sms_credit_for_number(db, user.id, num.id)
        result.append({
            "id": str(num.id),
            "phone_number": num.phone_number,
            "country": num.country,
            "provider": num.provider,
            "purchased_at": num.purchased_at.isoformat() if num.purchased_at else None,
            "expires_at": num.expires_at.isoformat() if num.expires_at else None,
            "is_active": num.is_active,
            "sms_credits": {
                "total": credit.total_credits if credit else 0,
                "used": credit.used_credits if credit else 0,
                "remaining": (credit.total_credits - credit.used_credits) if credit else 0,
            } if credit else None,
        })

    return {"numbers": result}


# ---------------------------------------------------------------------------
# 5. GET /sms/web/{number_id}
# ---------------------------------------------------------------------------

@router.get("/sms/web/{number_id}")
async def get_web_sms_logs(number_id: str, db: AsyncSession = Depends(get_db)):
    try:
        nid = uuid.UUID(number_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid number_id UUID")

    logs = await crud.get_sms_logs_for_number(db, nid)
    return {
        "sms_logs": [
            {
                "id": str(log.id),
                "from_number": log.from_number,
                "body": log.body,
                "received_at": log.received_at.isoformat() if log.received_at else None,
                "delivered": log.delivered,
            }
            for log in logs
        ]
    }


# ---------------------------------------------------------------------------
# 6. POST /auth/web/register
# ---------------------------------------------------------------------------

@router.post("/auth/web/register")
async def register_web_user(req: RegisterWebUserRequest, db: AsyncSession = Depends(get_db)):
    existing = await crud.get_user_by_supabase_id(db, req.supabase_id)
    if existing:
        return {"status": "exists", "user_id": str(existing.id)}

    if req.email:
        existing_email = await crud.get_user_by_email(db, req.email)
        if existing_email:
            # Link supabase_id to existing email user
            existing_email.supabase_id = req.supabase_id
            await db.commit()
            return {"status": "linked", "user_id": str(existing_email.id)}

    user = await crud.create_web_user(
        db,
        email=req.email,
        full_name=req.full_name,
        supabase_id=req.supabase_id,
    )
    return {"status": "created", "user_id": str(user.id)}


# ---------------------------------------------------------------------------
# 7. POST /auth/web/verify
# ---------------------------------------------------------------------------

@router.post("/auth/web/verify")
async def verify_web_user(req: VerifyWebUserRequest, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_supabase_id(db, req.supabase_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": str(user.id),
        "email": user.email,
        "username": user.username,
        "joined_at": user.joined_at.isoformat() if user.joined_at else None,
        "number_limit": user.number_limit,
        "is_banned": user.is_banned,
    }
