import os
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

CUSTOMER_BOT_TOKEN = os.getenv("CUSTOMER_BOT_TOKEN", "")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")

_customer_bot: Bot = None
_admin_bot: Bot = None


def get_customer_bot() -> Bot:
    global _customer_bot
    if _customer_bot is None:
        _customer_bot = Bot(token=CUSTOMER_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _customer_bot


def get_admin_bot() -> Bot:
    global _admin_bot
    if _admin_bot is None:
        _admin_bot = Bot(token=ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _admin_bot


async def notify_user(telegram_id: str, message: str):
    bot = get_customer_bot()
    try:
        await bot.send_message(chat_id=telegram_id, text=message, disable_web_page_preview=True)
    except Exception:
        pass


async def notify_admins(message: str):
    admin_ids = os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    bot = get_admin_bot()
    for admin_id in admin_ids:
        admin_id = admin_id.strip()
        if admin_id:
            try:
                await bot.send_message(chat_id=admin_id, text=message, disable_web_page_preview=True)
            except Exception:
                pass


async def forward_sms_to_user(telegram_id: str, phone_number: str, from_number: str, body: str, remaining_credits: int):
    msg = (
        f"📩 <b>New SMS Received</b>\n\n"
        f"📱 <b>Your Number:</b> <code>{phone_number}</code>\n"
        f"✉️ <b>From:</b> <code>{from_number}</code>\n"
        f"📝 <b>Message:</b>\n<code>{body}</code>\n\n"
        f"💳 <b>SMS Credits Left:</b> {remaining_credits}"
    )
    await notify_user(telegram_id, msg)


async def send_low_credit_warning(telegram_id: str, phone_number: str, remaining: int):
    msg = (
        f"⚠️ <b>Low SMS Credit Warning</b>\n\n"
        f"📱 <b>Number:</b> <code>{phone_number}</code>\n"
        f"💳 <b>Credits Left:</b> {remaining}\n\n"
        f"You are running low on SMS credits. Top up now to avoid missing important verification codes."
    )
    await notify_user(telegram_id, msg)


