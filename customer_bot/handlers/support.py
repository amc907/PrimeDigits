import os
from aiogram import Router, F
from aiogram.types import CallbackQuery

from customer_bot.keyboards.menus import support_menu, main_menu

router = Router()

ADMIN_BOT_LINK = os.getenv("ADMIN_BOT_LINK", "https://t.me/PrimeDigitsSupportBot")


@router.callback_query(F.data == "menu_support")
async def menu_support(callback: CallbackQuery):
    await callback.message.edit_text(
        "🆘 <b>Support</b>\n\n"
        "Need help? Click the button below to chat with our support team.\n\n"
        "Common issues:\n"
        "• Number not receiving SMS\n"
        "• Payment issues\n"
        "• Account questions\n\n"
        "We're here to help!",
        reply_markup=support_menu(ADMIN_BOT_LINK),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "menu_referral")
async def menu_referral(callback: CallbackQuery):
    from database.connection import AsyncSessionLocal
    from database import crud
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, str(callback.from_user.id))
        code = user.referral_code if user else "N/A"
        referrals = user.referrals_made if user else []
        count = len(referrals)
        rewarded = sum(1 for r in referrals if r.reward_given)

    link = f"https://t.me/PrimeDigitsBot?start={code}"
    text = (
        f"🤝 <b>Refer & Earn</b>\n\n"
        f"Invite your friends to PrimeDigits and earn <b>5 FREE SMS credits</b> for each friend who buys a number!\n\n"
        f"📊 <b>Your Stats</b>\n"
        f"👥 Invited: {count}\n"
        f"✅ Rewarded: {rewarded}\n\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{link}</code>\n\n"
        f"Share this link with friends and start earning!"
    )
    await callback.message.edit_text(
        text,
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()
