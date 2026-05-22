import logging
from fastapi import APIRouter, Request
from database.connection import AsyncSessionLocal
from database import crud
from utils.notifications import (
    forward_sms_to_user, send_low_credit_warning
)

router = APIRouter(
    prefix="/webhooks/telnyx",
    tags=["telnyx"]
)
logger = logging.getLogger(__name__)


@router.post("/sms")
async def telnyx_sms_webhook(request: Request):
    try:
        payload = await request.json()
        data = payload.get("data", {})
        event_type = data.get("event_type", "")

        if event_type != \
                "message.received":
            return {"status": "ignored"}

        payload_data = data.get("payload", {})
        to_list = payload_data.get("to", [])
        from_info = payload_data.get("from", {})

        to_number = to_list[0].get(
            "phone_number", ""
        ) if to_list else ""
        from_number = from_info.get(
            "phone_number", ""
        )
        body = payload_data.get("text", "")

        if not to_number:
            return {"status": "ignored"}

        async with AsyncSessionLocal() as db:
            from database.models import Number
            from sqlalchemy import select
            result = await db.execute(
                select(Number).where(
                    Number.phone_number == to_number
                )
            )
            number = result.scalar_one_or_none()

            if not number or not number.is_active:
                return {"status": "ignored"}

            user = number.user
            if not user or user.is_banned:
                return {"status": "ignored"}

            success = await crud.deduct_sms_credit(
                db, user.id, number.id
            )
            credit = await \
                crud.get_sms_credit_for_number(
                db, user.id, number.id
            )
            remaining = (
                credit.total_credits -
                credit.used_credits
            ) if credit else 0

            await crud.create_sms_log(
                db,
                number_id=number.id,
                from_number=from_number,
                body=body,
                delivered=success,
                credit_deducted=success
            )

            if success:
                await forward_sms_to_user(
                    user.telegram_id,
                    number.phone_number,
                    from_number,
                    body,
                    remaining
                )
                if remaining <= 5:
                    await send_low_credit_warning(
                        user.telegram_id,
                        number.phone_number,
                        remaining
                    )
            else:
                await forward_sms_to_user(
                    user.telegram_id,
                    number.phone_number,
                    from_number,
                    "[Message blocked — insufficient "
                    "SMS credits. Please top up.]",
                    remaining
                )

        return {"status": "ok"}

    except Exception as e:
        logger.exception(
            f"Telnyx webhook error: {e}"
        )
        return {"status": "error"}
