from datetime import datetime
from aiogram import Router, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import AsyncSessionLocal
from database import crud
from customer_bot.keyboards.menus import main_menu, number_actions_menu, confirm_payment_menu, back_to_main
from providers.twilio_provider import TwilioProvider
from providers.telnyx_provider import TelnyxProvider

router = Router()

RENEW_PRICING = {
    1: 3000,
    3: 8000,
    6: 14000,
    12: 25000,
}


@router.callback_query(F.data == "menu_numbers")
async def menu_numbers(callback: CallbackQuery):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, str(callback.from_user.id))
        if not user:
            await callback.answer("Please start the bot first.", show_alert=True)
            return

        numbers = await crud.get_active_numbers_for_user(db, user.id)

        if not numbers:
            await callback.message.edit_text(
                "📭 You don't have any active numbers yet.\n\nTap 🛒 Buy Number to get started!",
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        text = "📱 <b>Your Active Numbers</b>\n\n"
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = []
        for n in numbers:
            credit = await crud.get_sms_credit_for_number(db, user.id, n.id)
            remaining = credit.total_credits - credit.used_credits if credit else 0
            text += (
                f"<code>{n.phone_number}</code>\n"
                f"🌍 {n.country} | ⏳ Expires: {n.expires_at.strftime('%Y-%m-%d')}\n"
                f"💳 Credits: {remaining}\n\n"
            )
            kb.append([InlineKeyboardButton(text=n.phone_number, callback_data=f"numact_{n.id}")])

        kb.append([InlineKeyboardButton(text="🔙 Main Menu", callback_data="menu_back")])
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML"
        )
        await callback.answer()


@router.callback_query(F.data.startswith("numact_"))
async def number_actions(callback: CallbackQuery):
    number_id = callback.data.split("_", 1)[1]
    async with AsyncSessionLocal() as db:
        number = await crud.get_number_by_id(db, number_id)
        credit = await crud.get_sms_credit_for_number(db, number.user_id, number.id) if number else None

    if not number:
        await callback.answer("Number not found.", show_alert=True)
        return

    remaining = credit.total_credits - credit.used_credits if credit else 0
    text = (
        f"📱 <b>{number.phone_number}</b>\n\n"
        f"🌍 Country: {number.country}\n"
        f"⏳ Expires: {number.expires_at.strftime('%Y-%m-%d')}\n"
        f"💳 SMS Credits: {remaining}\n\n"
        f"What would you like to do?"
    )
    await callback.message.edit_text(
        text,
        reply_markup=number_actions_menu(str(number.id)),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("renew_"))
async def renew_number(callback: CallbackQuery):
    number_id = callback.data.split("_", 1)[1]
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = [
        [InlineKeyboardButton(text="1 Month — ₦3,000", callback_data=f"rencon_{number_id}_1")],
        [InlineKeyboardButton(text="3 Months — ₦8,000", callback_data=f"rencon_{number_id}_3")],
        [InlineKeyboardButton(text="6 Months — ₦14,000", callback_data=f"rencon_{number_id}_6")],
        [InlineKeyboardButton(text="1 Year — ₦25,000", callback_data=f"rencon_{number_id}_12")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=f"numact_{number_id}")],
    ]
    await callback.message.edit_text(
        "⏳ Choose renewal duration:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rencon_"))
async def confirm_renewal(callback: CallbackQuery):
    parts = callback.data.split("_", 2)
    _, number_id, months = parts
    months = int(months)
    price = RENEW_PRICING[months]
    async with AsyncSessionLocal() as db:
        number = await crud.get_number_by_id(db, number_id)
    if not number:
        await callback.answer("Number not found.", show_alert=True)
        return

    text = (
        f"🔄 <b>Renewal Summary</b>\n\n"
        f"📱 Number: <code>{number.phone_number}</code>\n"
        f"⏳ Duration: {months} month{'s' if months>1 else ''}\n"
        f"💰 Price: ₦{price:,}\n\n"
        f"Proceed to payment?"
    )
    await callback.message.edit_text(
        text,
        reply_markup=confirm_payment_menu(f"renew_{number_id}_{months}_{price}"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_renew_"))
async def process_renewal_payment(callback: CallbackQuery):
    parts = callback.data.split("_", 4)
    _, _, number_id, months, price = parts
    months = int(months)
    price = int(price)

    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, str(callback.from_user.id))
        if not user or user.is_banned:
            await callback.answer("Access denied.", show_alert=True)
            return

        tx = await crud.create_transaction(db, user.id, float(price), f"renew_{months}", flutterwave_ref=f"MOCK_RENEW_{number_id}")
        await crud.update_transaction_status(db, tx.id, "completed")

        number = await crud.renew_number(db, number_id, months)

    await callback.message.edit_text(
        f"✅ <b>Renewal Successful!</b>\n\n"
        f"📱 <code>{number.phone_number}</code>\n"
        f"⏳ New expiry: {number.expires_at.strftime('%Y-%m-%d')}\n\n"
        f"Your number is safe and active!",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "menu_history")
async def menu_history(callback: CallbackQuery):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, str(callback.from_user.id))
        if not user:
            await callback.answer("Please start the bot first.", show_alert=True)
            return

        numbers = await crud.get_active_numbers_for_user(db, user.id)

        if not numbers:
            await callback.message.edit_text(
                "📭 You don't have any active numbers yet.\n\nTap 🛒 Buy Number to get started!",
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        text = "📜 <b>Select a number to view SMS History:</b>\n\n"
        kb = []
        for n in numbers:
            text += f"<code>{n.phone_number}</code> — {n.country}\n"
            kb.append([InlineKeyboardButton(text=n.phone_number, callback_data=f"hist_{n.id}")])

        kb.append([InlineKeyboardButton(text="🔙 Main Menu", callback_data="menu_back")])
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML"
        )
        await callback.answer()


@router.callback_query(F.data.startswith("hist_"))
async def view_history(callback: CallbackQuery):
    number_id = callback.data.split("_", 1)[1]
    async with AsyncSessionLocal() as db:
        logs = await crud.get_sms_logs_for_number(db, number_id)
        number = await crud.get_number_by_id(db, number_id)

    if not logs:
        await callback.message.edit_text(
            "📭 No SMS history for this number yet.",
            reply_markup=back_to_main(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    text = f"📜 <b>SMS History for {number.phone_number if number else 'Number'}</b>\n\n"
    for log in logs[:20]:
        preview = log.body[:100] + "..." if len(log.body) > 100 else log.body
        text += (
            f"📩 <b>From:</b> <code>{log.from_number}</code>\n"
            f"📝 {preview}\n"
            f"🕒 {log.received_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        )

    await callback.message.edit_text(
        text,
        reply_markup=back_to_main(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_"))
async def delete_number_confirm(callback: CallbackQuery):
    number_id = callback.data.split("_", 1)[1]
    async with AsyncSessionLocal() as db:
        number = await crud.get_number_by_id(db, number_id)

    if not number:
        await callback.answer("Number not found.", show_alert=True)
        return

    text = (
        f"⚠️ Are you sure you want to delete <code>{number.phone_number}</code>?\n\n"
        f"This is permanent and NO REFUND will be given."
    )
    kb = [
        [InlineKeyboardButton(text="Yes, Delete ✅", callback_data=f"delconf_{number_id}")],
        [InlineKeyboardButton(text="Cancel ❌", callback_data=f"numact_{number_id}")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("delconf_"))
async def delete_number_confirmed(callback: CallbackQuery):
    number_id = callback.data.split("_", 1)[1]
    async with AsyncSessionLocal() as db:
        number = await crud.get_number_by_id(db, number_id)
        if not number:
            await callback.answer("Number not found.", show_alert=True)
            return

        # Release from provider
        if number.provider == "twilio":
            provider = TwilioProvider()
        else:
            provider = TelnyxProvider()

        if number.number_sid and not number.number_sid.startswith("MOCK_"):
            await provider.release_number(number.number_sid)

        # Log deletion
        await crud.log_number_deletion(
            db,
            number_id=number.id,
            phone_number=number.phone_number,
            deleted_by_telegram_id=str(callback.from_user.id)
        )

        # Delete number, logs, credits
        await crud.delete_number_and_logs(db, number.id)

    await callback.message.edit_text(
        f"🗑 <b>Number Deleted</b>\n\n"
        f"<code>{number.phone_number}</code> has been permanently deleted.\n\n"
        f"You can now purchase a new number if you wish.",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

    # Notify admins
    from utils.notifications import notify_admins
    admin_name = callback.from_user.full_name or callback.from_user.username or f"ID {callback.from_user.id}"
    await notify_admins(
        f"🗑 <b>Number Deleted</b>\n\n"
        f"📱 <code>{number.phone_number}</code>\n"
        f"👤 By: {admin_name} (<code>{callback.from_user.id}</code>)\n"
        f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )

