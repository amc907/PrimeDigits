import uuid
import os
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import AsyncSessionLocal
from database import crud
from customer_bot.keyboards.menus import country_menu, duration_menu, confirm_payment_menu, main_menu
from providers.telnyx_provider import TelnyxProvider

router = Router()
logger = logging.getLogger(__name__)
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")

PRICING = {
    "us": {1: 3000, 3: 8000, 6: 14000, 12: 25000},
    "ca": {1: 3000, 3: 8000, 6: 14000, 12: 25000},
}


@router.callback_query(F.data == "menu_buy")
async def menu_buy(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌍 Choose a country for your virtual number:",
        reply_markup=country_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("country_"))
async def choose_country(callback: CallbackQuery):
    country = callback.data.split("_")[1]
    await callback.message.edit_text(
        f"⏳ Choose subscription duration for your {'🇺🇸 US' if country=='us' else '🇨🇦 Canada'} number:",
        reply_markup=duration_menu(country),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dur_"))
async def choose_duration(callback: CallbackQuery):
    parts = callback.data.split("_", 2)
    _, country, months = parts
    months = int(months)
    price = PRICING.get(country, PRICING["us"])[months]
    text = (
        f"📋 <b>Order Summary</b>\n\n"
        f"🌍 Country: {'🇺🇸 US' if country=='us' else '🇨🇦 Canada'}\n"
        f"⏳ Duration: {months} month{'s' if months>1 else ''}\n"
        f"💰 Price: ₦{price:,}\n"
        f"📩 SMS Credits: 15 included\n\n"
        f"Proceed to payment?"
    )
    await callback.message.edit_text(
        text,
        reply_markup=confirm_payment_menu(f"{country}_{months}_{price}"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery):
    parts = callback.data.split("_", 3)
    _, country, months, price = parts
    months = int(months)
    price = int(price)

    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, str(callback.from_user.id))
        if not user or user.is_banned:
            await callback.answer("User not found or banned.", show_alert=True)
            return

        numbers = await crud.get_active_numbers_for_user(db, user.id)
        limit = user.number_limit or 3
        if len(numbers) >= limit:
            await callback.message.edit_text(
                f"⚠️ You've reached your limit of {limit} numbers. "
                f"Delete an existing number or contact support to increase your limit.",
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Mock Flutterwave payment
        tx = await crud.create_transaction(db, user.id, float(price), f"number_{country}_{months}", flutterwave_ref=f"MOCK_{uuid.uuid4().hex[:12]}")
        await crud.update_transaction_status(db, tx.id, "completed")

        # Purchase number (Telnyx for all countries)
        provider = TelnyxProvider()
        provider_name = "telnyx"
        numbers = await provider.search_numbers(country)

        if not numbers:
            await callback.message.edit_text(
                "❌ No numbers available right now. Please try again later or contact support.",
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        chosen = numbers[0]
        result = await provider.purchase_number(chosen["phone_number"])

        # Configure webhook
        webhook_url = f"{WEBHOOK_BASE_URL}/webhooks/telnyx/sms"
        if WEBHOOK_BASE_URL and not result["sid"].startswith("MOCK_"):
            await provider.configure_webhook(result["sid"], webhook_url)

        number = await crud.create_number(
            db, user.id, result["phone_number"], result["sid"],
            provider_name,
            country.upper(), months
        )
        await crud.get_or_create_sms_credit(db, user.id, number.id, initial=15)

        await callback.message.edit_text(
            f"🎉 <b>Payment Successful!</b>\n\n"
            f"📱 <b>Your Number:</b> <code>{result['phone_number']}</code>\n"
            f"🌍 <b>Country:</b> {country.upper()}\n"
            f"⏳ <b>Expires:</b> {number.expires_at.strftime('%Y-%m-%d')}\n"
            f"💳 <b>SMS Credits:</b> 15\n\n"
            f"Use this number for verifications. You will receive SMS directly here!",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        await callback.answer()
