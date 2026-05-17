from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import AsyncSessionLocal
from database import crud
from customer_bot.keyboards.menus import credit_menu, confirm_payment_menu, main_menu, back_to_main

router = Router()

CREDIT_PACKS = {
    "20_2000": (20, 2000),
    "50_4500": (50, 4500),
    "100_8000": (100, 8000),
}

user_credit_context = {}


@router.callback_query(F.data == "menu_credits")
async def menu_credits(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 <b>Buy SMS Credits</b>\n\n"
        "Top up SMS credits for any of your active numbers.\n\n"
        "Choose a package:",
        reply_markup=credit_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cred_"))
async def choose_credit_pack(callback: CallbackQuery):
    pack = callback.data.replace("cred_", "")
    if pack not in CREDIT_PACKS:
        await callback.answer("Invalid package.", show_alert=True)
        return

    qty, price = CREDIT_PACKS[pack]
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, str(callback.from_user.id))
        numbers = await crud.get_active_numbers_for_user(db, user.id) if user else []

    if not numbers:
        await callback.message.edit_text(
            "❌ You don't have any active numbers. Buy a number first!",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Show number selection for top-up
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = []
    for n in numbers:
        kb.append([InlineKeyboardButton(text=n.phone_number, callback_data=f"topupnum_{n.id}_{qty}_{price}")])
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_credits")])

    await callback.message.edit_text(
        f"📱 Select the number to receive {qty} SMS credits:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topupnum_"))
async def confirm_credit_topup(callback: CallbackQuery):
    parts = callback.data.split("_", 3)
    _, number_id, qty, price = parts
    qty = int(qty)
    price = int(price)

    async with AsyncSessionLocal() as db:
        number = await crud.get_number_by_id(db, number_id)
    if not number:
        await callback.answer("Number not found.", show_alert=True)
        return

    text = (
        f"📋 <b>Top-up Summary</b>\n\n"
        f"📱 Number: <code>{number.phone_number}</code>\n"
        f"➕ Credits: {qty}\n"
        f"💰 Price: ₦{price:,}\n\n"
        f"Proceed to payment?"
    )
    await callback.message.edit_text(
        text,
        reply_markup=confirm_payment_menu(f"credit_{number_id}_{qty}_{price}"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_credit_"))
async def process_credit_payment(callback: CallbackQuery):
    parts = callback.data.split("_", 4)
    _, _, number_id, qty, price = parts
    qty = int(qty)
    price = int(price)

    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, str(callback.from_user.id))
        if not user or user.is_banned:
            await callback.answer("User not found or banned.", show_alert=True)
            return

        tx = await crud.create_transaction(db, user.id, float(price), f"credit_topup_{qty}", flutterwave_ref=f"MOCK_{qty}_{price}")
        await crud.update_transaction_status(db, tx.id, "completed")

        credit = await crud.add_sms_credits(db, user.id, number_id, qty)
        remaining = credit.total_credits - credit.used_credits
        number = await crud.get_number_by_id(db, number_id)

    await callback.message.edit_text(
        f"✅ <b>Payment Successful!</b>\n\n"
        f"📱 <b>Number:</b> <code>{number.phone_number}</code>\n"
        f"➕ <b>Credits Added:</b> {qty}\n"
        f"💳 <b>Total Remaining:</b> {remaining}\n\n"
        f"Thank you for using PrimeDigits!",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_"))
async def topup_from_number(callback: CallbackQuery):
    number_id = callback.data.split("_", 1)[1]
    await callback.message.edit_text(
        "💳 Choose a top-up package:",
        reply_markup=credit_menu(),
        parse_mode="HTML"
    )
    user_credit_context[callback.from_user.id] = number_id
    await callback.answer()
