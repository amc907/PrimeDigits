import os
import logging
from fastapi import APIRouter, Request, Form
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import AsyncSessionLocal
from database import crud
from utils.notifications import forward_sms_to_user, send_low_credit_warning

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])
logger = logging.getLogger(__name__)

WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")


@router.post("/sms")
async def twilio_sms_webhook(
    request: Request,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(default="")
):
    # Twilio signature validation
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        form_data = await request.form()
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)

        if not validator.validate(url, dict(form_data), signature):
            logger.warning("Invalid Twilio signature!")
            return {"status": "forbidden"}
    except Exception as e:
        logger.warning(f"Twilio validation skipped or failed: {e}")

    async with AsyncSessionLocal() as db:
        # Find the number in our DB
        from database.models import Number
        from sqlalchemy import select
        result = await db.execute(select(Number).where(Number.phone_number == To))
        number = result.scalar_one_or_none()

        if not number or not number.is_active:
            logger.warning(f"SMS to unknown/inactive number: {To}")
            return {"status": "ignored"}

        user = number.user
        if not user or user.is_banned:
            return {"status": "ignored"}

        # Deduct credit
        success = await crud.deduct_sms_credit(db, user.id, number.id)
        credit = await crud.get_sms_credit_for_number(db, user.id, number.id)
        remaining = credit.total_credits - credit.used_credits if credit else 0

        # Log SMS
        await crud.create_sms_log(
            db,
            number_id=number.id,
            from_number=From,
            body=Body,
            delivered=success,
            credit_deducted=success
        )

        if success:
            await forward_sms_to_user(user.telegram_id, number.phone_number, From, Body, remaining)
            if remaining == 5:
                await send_low_credit_warning(user.telegram_id, number.phone_number, remaining)
        else:
            await forward_sms_to_user(
                user.telegram_id,
                number.phone_number,
                From,
                "[Message blocked — insufficient SMS credits. Please top up.]",
                remaining
            )

        return {"status": "ok"}
