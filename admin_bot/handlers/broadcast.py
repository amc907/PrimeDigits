import os
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from database.connection import AsyncSessionLocal
from database import crud
from utils.notifications import notify_user

router = Router()

ADMIN_IDS = [x.strip() for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.answer("Usage: /broadcast <message>", parse_mode="HTML")
        return

    broadcast_text = parts[1]
    async with AsyncSessionLocal() as db:
        users = await crud.get_all_users(db)
        sent = 0
        failed = 0
        for user in users:
            if user.is_banned:
                continue
            try:
                await notify_user(user.telegram_id, f"📢 <b>Announcement</b>\n\n{broadcast_text}")
                sent += 1
            except Exception:
                failed += 1
        await crud.create_announcement(db, broadcast_text, str(message.from_user.id))

    await message.answer(f"✅ Broadcast sent to {sent} users. Failed: {failed}.", parse_mode="HTML")
