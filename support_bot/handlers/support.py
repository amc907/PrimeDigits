import os
import re
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import CommandStart

from database.connection import AsyncSessionLocal
from database import crud

router = Router()
logger = logging.getLogger(__name__)

SUPPORT_GROUP_ID = os.getenv("SUPPORT_GROUP_ID", "")

try:
    _SUPPORT_GROUP_ID_INT = int(SUPPORT_GROUP_ID) if SUPPORT_GROUP_ID else 0
except ValueError:
    _SUPPORT_GROUP_ID_INT = 0


def _get_customer_prefix(name: str, user_id: int) -> str:
    return f"🆘 <b>Support Request</b>\n👤 <b>{name}</b>\n🆔 <code>{user_id}</code>\n\n"


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🆘 <b>PrimeDigits Support</b>\n\n"
        "Send us a message and our team will reply shortly.\n\n"
        "Please describe your issue in detail."
    )


@router.message(F.chat.type == "private")
async def customer_message(message: Message):
    if not _SUPPORT_GROUP_ID_INT:
        await message.answer("❌ Support is currently unavailable. Please try again later.")
        return

    customer_name = message.from_user.full_name or message.from_user.username or "Unknown"
    customer_id = str(message.from_user.id)
    prefix = _get_customer_prefix(customer_name, message.from_user.id)
    bot = message.bot

    group_msg = None

    try:
        if message.text:
            group_msg = await bot.send_message(
                chat_id=_SUPPORT_GROUP_ID_INT,
                text=prefix + message.text,
                parse_mode="HTML"
            )
        elif message.photo:
            caption = message.caption or ""
            group_msg = await bot.send_photo(
                chat_id=_SUPPORT_GROUP_ID_INT,
                photo=message.photo[-1].file_id,
                caption=prefix + caption,
                parse_mode="HTML"
            )
        elif message.document:
            caption = message.caption or ""
            group_msg = await bot.send_document(
                chat_id=_SUPPORT_GROUP_ID_INT,
                document=message.document.file_id,
                caption=prefix + caption,
                parse_mode="HTML"
            )
        elif message.voice:
            group_msg = await bot.send_voice(
                chat_id=_SUPPORT_GROUP_ID_INT,
                voice=message.voice.file_id,
                caption=prefix
            )
        elif message.video:
            caption = message.caption or ""
            group_msg = await bot.send_video(
                chat_id=_SUPPORT_GROUP_ID_INT,
                video=message.video.file_id,
                caption=prefix + caption,
                parse_mode="HTML"
            )
        elif message.sticker:
            info_msg = await bot.send_message(
                chat_id=_SUPPORT_GROUP_ID_INT,
                text=prefix + "[Sticker]",
                parse_mode="HTML"
            )
            group_msg = await bot.send_sticker(
                chat_id=_SUPPORT_GROUP_ID_INT,
                sticker=message.sticker.file_id
            )
            async with AsyncSessionLocal() as db:
                await crud.add_support_message_mapping(db, customer_id, info_msg.message_id)
                await crud.add_support_message_mapping(db, customer_id, group_msg.message_id)
            await message.answer("✅ Your message has been sent to our support team.")
            return
        else:
            info_msg = await bot.send_message(
                chat_id=_SUPPORT_GROUP_ID_INT,
                text=prefix + "[Unsupported message type]",
                parse_mode="HTML"
            )
            group_msg = await bot.forward_message(
                chat_id=_SUPPORT_GROUP_ID_INT,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            async with AsyncSessionLocal() as db:
                await crud.add_support_message_mapping(db, customer_id, info_msg.message_id)
                await crud.add_support_message_mapping(db, customer_id, group_msg.message_id)
            await message.answer("✅ Your message has been sent to our support team.")
            return

        if group_msg:
            async with AsyncSessionLocal() as db:
                await crud.add_support_message_mapping(db, customer_id, group_msg.message_id)

        await message.answer(
            "✅ Your message has been sent to our support team. We'll get back to you shortly."
        )
    except Exception as e:
        logger.exception("Failed to forward customer message to support group")
        await message.answer("❌ Failed to send your message. Please try again later.")


@router.message(F.chat.id == _SUPPORT_GROUP_ID_INT, F.reply_to_message)
async def group_reply(message: Message):
    bot = message.bot
    reply_to_id = message.reply_to_message.message_id

    async with AsyncSessionLocal() as db:
        mapping = await crud.get_support_mapping_by_group_message_id(db, reply_to_id)
        if not mapping:
            text = message.reply_to_message.text or message.reply_to_message.caption or ""
            match = re.search(r"🆔 <code>(\d+)</code>", text)
            if match:
                customer_id = match.group(1)
            else:
                await message.reply(
                    "⚠️ Could not find the customer for this message. "
                    "Make sure you're replying to a support request."
                )
                return
        else:
            customer_id = mapping.customer_telegram_id

    try:
        if message.text:
            await bot.send_message(chat_id=customer_id, text=message.text)
        elif message.photo:
            await bot.send_photo(
                chat_id=customer_id,
                photo=message.photo[-1].file_id,
                caption=message.caption
            )
        elif message.document:
            await bot.send_document(
                chat_id=customer_id,
                document=message.document.file_id,
                caption=message.caption
            )
        elif message.voice:
            await bot.send_voice(
                chat_id=customer_id,
                voice=message.voice.file_id,
                caption=message.caption
            )
        elif message.video:
            await bot.send_video(
                chat_id=customer_id,
                video=message.video.file_id,
                caption=message.caption
            )
        elif message.sticker:
            await bot.send_sticker(chat_id=customer_id, sticker=message.sticker.file_id)
        else:
            await message.reply("⚠️ Unsupported message type for reply.")
            return

        await message.reply("✅ Reply sent to customer.")
    except Exception as e:
        logger.exception("Failed to send reply to customer")
        await message.reply(f"❌ Failed to send reply to customer: {e}")
