import os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from database.connection import AsyncSessionLocal
from database import crud

router = Router()

ADMIN_IDS = [x.strip() for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]


def is_admin(tg_id: str) -> bool:
    return tg_id in ADMIN_IDS


@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(str(message.from_user.id)):
        await message.answer("🚫 Unauthorized access.", parse_mode="HTML")
        return

    text = (
        "👨‍💼 <b>PrimeDigits Admin Panel</b>\n\n"
        "Available commands:\n"
        "/stats — Daily & weekly stats\n"
        "/users — List users\n"
        "/pending — Pending payments\n"
        "/broadcast — Send message to all users\n"
        "/ban — Ban a user\n"
        "/unban — Unban a user\n"
        "/addagent — Add support agent\n"
        "/removeagent — Remove support agent\n"
        "/setlimit — Set number limit for user\n"
        "/addcredits — Add SMS credits to user\n"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(str(message.from_user.id)):
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    async with AsyncSessionLocal() as db:
        total_users = await crud.get_user_count(db)
        total_revenue = await crud.get_total_revenue(db)
        daily_revenue = await crud.get_revenue_since(db, datetime.utcnow() - timedelta(days=1))
        weekly_revenue = await crud.get_revenue_since(db, datetime.utcnow() - timedelta(days=7))
        pending = await crud.get_pending_transactions(db)
        pending_count = len(pending)

    text = (
        f"📊 <b>PrimeDigits Stats</b>\n\n"
        f"👥 Total Users: {total_users}\n"
        f"💰 Total Revenue: ₦{total_revenue:,.2f}\n"
        f"📅 Daily Revenue: ₦{daily_revenue:,.2f}\n"
        f"📆 Weekly Revenue: ₦{weekly_revenue:,.2f}\n"
        f"⏳ Pending Payments: {pending_count}\n"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("pending"))
async def cmd_pending(message: Message):
    if not is_admin(str(message.from_user.id)):
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    async with AsyncSessionLocal() as db:
        pending = await crud.get_pending_transactions(db)

    if not pending:
        await message.answer("✅ No pending payments.", parse_mode="HTML")
        return

    text = "⏳ <b>Pending Payments</b>\n\n"
    for tx in pending[:20]:
        user = tx.user
        username = user.username or f"ID {user.telegram_id}"
        text += (
            f"👤 {username}\n"
            f"💰 ₦{float(tx.amount_ngn):,.2f} | {tx.type}\n"
            f"🕒 {tx.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        )
    await message.answer(text, parse_mode="HTML")
