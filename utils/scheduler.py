import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import AsyncSessionLocal
from database import crud
from utils.notifications import notify_user, notify_admins
from providers.twilio_provider import TwilioProvider
from providers.telnyx_provider import TelnyxProvider

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler():
    scheduler.add_job(
        check_expiry_warnings,
        trigger=IntervalTrigger(hours=1),
        id="expiry_warnings",
        replace_existing=True
    )
    scheduler.add_job(
        check_release_expired_numbers,
        trigger=IntervalTrigger(hours=1),
        id="release_numbers",
        replace_existing=True
    )
    scheduler.add_job(
        check_low_credits,
        trigger=IntervalTrigger(hours=2),
        id="low_credits",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started")


async def check_expiry_warnings():
    async with AsyncSessionLocal() as db:
        for days in [7, 3, 1]:
            numbers = await crud.get_expiring_numbers(db, days)
            for number in numbers:
                if number.user:
                    msg = (
                        f"⏳ <b>Subscription Expiring Soon</b>\n\n"
                        f"📱 <b>Number:</b> <code>{number.phone_number}</code>\n"
                        f"⏰ <b>Expires In:</b> {days} day{'s' if days > 1 else ''}\n\n"
                        f"Renew now to keep your number active and avoid losing access."
                    )
                    await notify_user(number.user.telegram_id, msg)


async def check_release_expired_numbers():
    twilio = TwilioProvider()
    telnyx = TelnyxProvider()
    async with AsyncSessionLocal() as db:
        numbers = await crud.get_expired_numbers(db)
        for number in numbers:
            if number.expires_at and (datetime.utcnow() - number.expires_at).total_seconds() > 86400:
                if not number.number_sid or not number.number_sid.startswith("MOCK_"):
                    if number.provider == "telnyx":
                        await telnyx.release_number(number.number_sid)
                    else:
                        await twilio.release_number(number.number_sid)
                await crud.release_number(db, number.id)
                if number.user:
                    await notify_user(
                        number.user.telegram_id,
                        f"🔴 <b>Number Released</b>\n\n"
                        f"📱 <code>{number.phone_number}</code> has been released because your subscription expired and was not renewed."
                    )


async def check_low_credits():
    async with AsyncSessionLocal() as db:
        users = await crud.get_all_users(db)
        for user in users:
            for number in user.numbers:
                if not number.is_active:
                    continue
                credit = await crud.get_sms_credit_for_number(db, user.id, number.id)
                if credit:
                    remaining = credit.total_credits - credit.used_credits
                    if remaining == 5:
                        await notify_user(
                            user.telegram_id,
                            f"⚠️ <b>Low SMS Credit Warning</b>\n\n"
                            f"📱 <b>Number:</b> <code>{number.phone_number}</code>\n"
                            f"💳 <b>Credits Left:</b> {remaining}\n\n"
                            f"Top up now so you don't miss verification codes."
                        )
