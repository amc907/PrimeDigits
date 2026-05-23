import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import AsyncSessionLocal
from database import crud
from customer_bot.keyboards.menus import main_menu, country_menu

router = Router()
ADMIN_BOT_USERNAME = os.getenv("ADMIN_BOT_USERNAME", "PrimeDigitsSupportBot")
SUPPORT_BOT_LINK = os.getenv("SUPPORT_BOT_LINK") or os.getenv("ADMIN_BOT_LINK", "https://t.me/PrimeDigitsSupportBot")


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


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>How PrimeDigits Works</b>\n\n"
        "📱 <b>STEP 1 — Buy a Number</b>\n"
        "• Select duration & pay\n"
        "• Get number instantly with 15 FREE SMS\n\n"
        "💳 <b>STEP 2 — SMS Credits</b>\n"
        "• 1 code = 1 credit\n"
        "• Top up anytime\n"
        "• Credits never expire\n\n"
        "🔄 <b>STEP 3 — Renewal</b>\n"
        "• Renew before expiry to keep number\n"
        "• Warnings at 7, 3, 1 day before\n"
        "• Expired = number lost forever\n\n"
        "⚠️ Subscription ≠ Credits — manage both!"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🛒 Buy Number",
                    callback_data="menu_buy")],
                [InlineKeyboardButton(
                    text="🏠 Main Menu",
                    callback_data="menu_back")]
            ]),
        parse_mode="HTML"
    )


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    await message.answer(
        "🌍 Choose a country for your virtual number:",
        reply_markup=country_menu(),
        parse_mode="HTML"
    )


@router.message(Command("numbers"))
async def cmd_numbers(message: Message):
    # Reuse menu_numbers logic but for message
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(
            db, str(message.from_user.id))
        if not user:
            await message.answer("Please /start first.")
            return
        numbers = await crud.get_active_numbers_for_user(
            db, user.id)
        if not numbers:
            await message.answer(
                "📭 No active numbers yet.\n"
                "Use /buy to get started!",
                parse_mode="HTML"
            )
            return
        from aiogram.types import (
            InlineKeyboardMarkup, InlineKeyboardButton)
        text = "📱 <b>Your Active Numbers</b>\n\n"
        kb = []
        for n in numbers:
            credit = await crud.get_sms_credit_for_number(
                db, user.id, n.id)
            remaining = (credit.total_credits -
                credit.used_credits) if credit else 0
            text += (
                f"<code>{n.phone_number}</code>\n"
                f"🌍 {n.country} | "
                f"⏳ {n.expires_at.strftime('%Y-%m-%d')}\n"
                f"💳 Credits: {remaining}\n\n"
            )
            kb.append([InlineKeyboardButton(
                text=n.phone_number,
                callback_data=f"numact_{n.id}")])
        kb.append([InlineKeyboardButton(
            text="🔙 Main Menu",
            callback_data="menu_back")])
        await message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=kb),
            parse_mode="HTML"
        )


@router.message(Command("credits"))
async def cmd_credits(message: Message):
    from customer_bot.keyboards.menus import credit_menu
    await message.answer(
        "💳 <b>Buy SMS Credits</b>\n\n"
        "Choose a package:",
        reply_markup=credit_menu(),
        parse_mode="HTML"
    )


@router.message(Command("history"))
async def cmd_history(message: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(
            db, str(message.from_user.id))
        if not user:
            await message.answer("Please /start first.")
            return
        numbers = await crud.get_active_numbers_for_user(
            db, user.id)
        if not numbers:
            await message.answer(
                "📭 No active numbers yet.\n"
                "Use /buy to get started!"
            )
            return
        from aiogram.types import (
            InlineKeyboardMarkup, InlineKeyboardButton)
        text = "📜 <b>Select number to view history:</b>\n\n"
        kb = []
        for n in numbers:
            text += f"<code>{n.phone_number}</code> — {n.country}\n"
            kb.append([InlineKeyboardButton(
                text=n.phone_number,
                callback_data=f"hist_{n.id}")])
        kb.append([InlineKeyboardButton(
            text="🔙 Main Menu",
            callback_data="menu_back")])
        await message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=kb),
            parse_mode="HTML"
        )


@router.message(Command("howto"))
async def cmd_howto(message: Message):
    from aiogram.types import (
        InlineKeyboardMarkup, InlineKeyboardButton)
    text = (
        "📖 <b>How PrimeDigits Works</b>\n\n"
        "📱 <b>STEP 1 — Buy a Number</b>\n"
        "• Choose country (US 🇺🇸, UK 🇬🇧, CA 🇨🇦)\n""• Select duration & pay\n"
        "• Get number instantly with 15 FREE SMS\n\n"
        "💳 <b>STEP 2 — SMS Credits</b>\n"
        "• 1 code = 1 credit\n"
        "• Top up anytime\n"
        "• Credits never expire\n\n"
        "🔄 <b>STEP 3 — Renewal</b>\n"
        "• Renew before expiry to keep number\n"
        "• Warnings at 7, 3, 1 day before\n"
        "• Expired = number lost forever\n\n"
        "⚠️ Subscription ≠ Credits — manage both!"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🛒 Buy Number",
                    callback_data="menu_buy")],
                [InlineKeyboardButton(
                    text="🏠 Main Menu",
                    callback_data="menu_back")]
            ]),
        parse_mode="HTML"
    )


@router.message(Command("support"))
async def cmd_support(message: Message):
    from customer_bot.keyboards.menus import support_menu
    await message.answer(
        "🆘 <b>Support</b>\n\n"
        "Need help? Tap below to chat with our team.",
        reply_markup=support_menu(SUPPORT_BOT_LINK),
        parse_mode="HTML"
    )


@router.message(Command("referral"))
async def cmd_referral(message: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(
            db, str(message.from_user.id))
        code = user.referral_code if user else "N/A"
        referrals = user.referrals_made if user else []
        count = len(referrals)
        rewarded = sum(
            1 for r in referrals if r.reward_given)
    link = f"https://t.me/PrimeDigitsBot?start={code}"
    await message.answer(
        f"🤝 <b>Refer & Earn</b>\n\n"
        f"Earn <b>5 FREE SMS credits</b> per referral!\n\n"
        f"👥 Invited: {count}\n"
        f"✅ Rewarded: {rewarded}\n\n"
        f"🔗 Your link:\n<code>{link}</code>",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


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
