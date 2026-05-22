import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import AsyncSessionLocal
from database import crud
from customer_bot.keyboards.menus import main_menu

router = Router()
ADMIN_BOT_USERNAME = os.getenv("ADMIN_BOT_USERNAME", "PrimeDigitsSupportBot")


WELCOME_TEXT = (
    "👋 <b>Welcome to PrimeDigits!</b>\n\n"
    "Your trusted virtual phone number partner for developers and freelancers worldwide.\n\n"
    "🚀 <b>Why PrimeDigits?</b>\n"
    "• Get USA 🇺🇸, Canada 🇨🇦 & UK 🇬🇧 numbers instantly\n"
    "• Other platforms charge ₦800–₦1,500 per <u>single</u> verification code\n"
    "• PrimeDigits gives you <b>15 FREE SMS credits</b> with every number — use them for multiple verifications!\n"
    "• Top up SMS credits anytime at unbeatable rates\n"
    "• Your number stays active as long as your subscription is valid\n\n"
    "💼 Perfect for Upwork, Fiverr, PayPal, Wise, Telegram, WhatsApp & more.\n\n"
    "Tap <b>🛒 Buy Number</b> to get started!"
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, str(message.from_user.id))
        if not user:
            args = message.text.split()[1] if len(message.text.split()) > 1 else None
            user = await crud.create_user(
                db,
                telegram_id=str(message.from_user.id),
                username=message.from_user.username,
                referred_by_code=args if args and args != "None" else None
            )
        if user.is_banned:
            await message.answer("🚫 Your account has been suspended. Contact support for assistance.", parse_mode="HTML")
            return

        # Update username if changed
        if user.username != message.from_user.username:
            await crud.update_username(
                db,
                str(message.from_user.id),
                message.from_user.username
            )

    await message.answer(WELCOME_TEXT, reply_markup=main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "menu_howto")
async def menu_howto(callback: CallbackQuery):
    text = (
        "📖 <b>How PrimeDigits Works</b>\n\n"
        "📱 <b>STEP 1 — Buy a Number</b>\n"
        "• Choose your country (US 🇺🇸, UK 🇬🇧, "
        "Canada 🇨🇦)\n"
        "• Select subscription duration\n"
        "• Pay and receive your number instantly\n"
        "• Every number comes with "
        "<b>15 FREE SMS credits</b>\n\n"
        "💳 <b>STEP 2 — SMS Credits</b>\n"
        "• Each verification code = 1 SMS credit\n"
        "• When credits run out → top up anytime\n"
        "• Your number stays active even with "
        "0 credits\n"
        "• Credits never expire\n\n"
        "🔄 <b>STEP 3 — Renewing Your Number</b>\n"
        "• Your number has an expiry date\n"
        "• Renew BEFORE expiry to keep same number\n"
        "• Warnings sent at 7, 3, and 1 day before\n"
        "• If expired and not renewed → "
        "number is gone forever\n"
        "• Buying SMS credits does NOT renew "
        "your number\n\n"
        "⚠️ <b>IMPORTANT — Subscription vs Credits</b>\n"
        "• <b>Subscription</b> = how long you OWN "
        "the number\n"
        "• <b>SMS Credits</b> = how many codes "
        "you can receive\n"
        "• These are TWO separate things!\n"
        "• Example: Active number with 0 credits "
        "= SMS blocked\n"
        "• Example: Credits remaining but expired "
        "number = no number\n"
        "• Manage BOTH to keep your service "
        "working!\n\n"
        "💰 <b>SMS Credit Top-ups</b>\n"
        "• Starter: 20 SMS = ₦2,000\n"
        "• Standard: 50 SMS = ₦4,500\n"
        "• Premium: 100 SMS = ₦8,000\n\n"
        "❓ Need help? Tap 🆘 Support anytime!"
    )
    from aiogram.types import (
        InlineKeyboardMarkup, InlineKeyboardButton
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🛒 Buy a Number",
            callback_data="menu_buy"
        )],
        [InlineKeyboardButton(
            text="🔙 Main Menu",
            callback_data="menu_back"
        )]
    ])
    await callback.message.edit_text(
        text, reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "menu_back")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu(), parse_mode="HTML")
    await callback.answer()
