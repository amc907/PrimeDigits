import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.exc import IntegrityError

from database.connection import AsyncSessionLocal
from database import crud
from providers.twilio_provider import TwilioProvider
from providers.telnyx_provider import TelnyxProvider

router = Router()

ADMIN_IDS = [x.strip() for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]


def is_admin_or_agent(tg_id: str) -> bool:
    return tg_id in ADMIN_IDS  # agents checked separately in commands that allow them


@router.message(Command("users"))
async def cmd_users(message: Message):
    tg_id = str(message.from_user.id)
    if tg_id not in ADMIN_IDS:
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    async with AsyncSessionLocal() as db:
        users = await crud.get_all_users(db)

    if not users:
        await message.answer("No users found.", parse_mode="HTML")
        return

    text = f"👥 <b>Users ({len(users)})</b>\n\n"
    for u in users[:30]:
        numbers_count = len([n for n in u.numbers if n.is_active])
        status = "🚫 BANNED" if u.is_banned else "✅ Active"
        text += (
            f"@{u.username or 'N/A'} | ID: <code>{u.telegram_id}</code>\n"
            f"📱 Numbers: {numbers_count} | {status}\n\n"
        )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /ban <telegram_id>", parse_mode="HTML")
        return

    target_id = args[1]
    async with AsyncSessionLocal() as db:
        await crud.ban_user(db, target_id, True)
    await message.answer(f"🚫 User <code>{target_id}</code> has been banned.", parse_mode="HTML")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /unban <telegram_id>", parse_mode="HTML")
        return

    target_id = args[1]
    async with AsyncSessionLocal() as db:
        await crud.ban_user(db, target_id, False)
    await message.answer(f"✅ User <code>{target_id}</code> has been unbanned.", parse_mode="HTML")


@router.message(Command("replace"))
async def cmd_replace(message: Message):
    tg_id = str(message.from_user.id)
    if tg_id not in ADMIN_IDS:
        async with AsyncSessionLocal() as db:
            agent = await crud.get_support_agent(db, tg_id)
        if not agent or not agent.can_replace_numbers:
            await message.answer("🚫 You don't have permission to replace numbers.", parse_mode="HTML")
            return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("Usage: /replace <number_id> <country>", parse_mode="HTML")
        return

    number_id = args[1]
    country = args[2].lower()

    async with AsyncSessionLocal() as db:
        number = await crud.get_number_by_id(db, number_id)
        if not number:
            await message.answer("❌ Number not found.", parse_mode="HTML")
            return

        # Release old
        if number.number_sid and not number.number_sid.startswith("MOCK_"):
            twilio = TwilioProvider()
            await twilio.release_number(number.number_sid)

        # Get new
        if country == "uk":
            provider = TelnyxProvider()
            provider_name = "telnyx"
        else:
            provider = TwilioProvider()
            provider_name = "twilio"

        numbers = await provider.search_numbers(country)
        if not numbers:
            await message.answer("❌ No replacement numbers available.", parse_mode="HTML")
            return

        chosen = numbers[0]
        result = await provider.purchase_number(chosen["phone_number"])

        await crud.replace_number(db, number_id, result["phone_number"], result["sid"], provider_name)

    await message.answer(
        f"🔄 <b>Number Replaced</b>\n\n"
        f"Old: <code>{number.phone_number}</code>\n"
        f"New: <code>{result['phone_number']}</code>\n\n"
        f"Notify the user about the change.",
        parse_mode="HTML"
    )


@router.message(Command("addcredits"))
async def cmd_add_credits(message: Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) < 4:
        await message.answer("Usage: /addcredits <telegram_id> <number_id> <amount>", parse_mode="HTML")
        return

    _, tg_id, number_id, amount = args
    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, tg_id)
        if not user:
            await message.answer("❌ User not found.", parse_mode="HTML")
            return
        credit = await crud.add_sms_credits(db, user.id, number_id, int(amount))

    await message.answer(
        f"✅ Added {amount} SMS credits to user <code>{tg_id}</code>.\n"
        f"Total credits for number: {credit.total_credits}",
        parse_mode="HTML"
    )


@router.message(Command("addagent"))
async def cmd_add_agent(message: Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /addagent <telegram_id> [username]", parse_mode="HTML")
        return

    agent_tg_id = args[1]
    username = args[2] if len(args) > 2 else None
    async with AsyncSessionLocal() as db:
        try:
            await crud.add_support_agent(db, agent_tg_id, username, can_replace=True)
            await message.answer(f"✅ Support agent <code>{agent_tg_id}</code> added.", parse_mode="HTML")
        except IntegrityError:
            await db.rollback()
            await message.answer(f"⚠️ Agent <code>{agent_tg_id}</code> already exists.", parse_mode="HTML")
        except Exception as e:
            await db.rollback()
            await message.answer(f"❌ Error adding agent: {e}", parse_mode="HTML")


@router.message(Command("setlimit"))
async def cmd_set_limit(message: Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("Usage: /setlimit <telegram_id> <new_limit>", parse_mode="HTML")
        return

    target_id = args[1]
    try:
        new_limit = int(args[2])
    except ValueError:
        await message.answer("❌ Limit must be a number.", parse_mode="HTML")
        return

    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_telegram_id(db, target_id)
        if not user:
            await message.answer("❌ User not found.", parse_mode="HTML")
            return
        await crud.set_user_number_limit(db, user.id, new_limit)

    await message.answer(
        f"✅ User <code>{target_id}</code> number limit set to <b>{new_limit}</b>.",
        parse_mode="HTML"
    )


@router.message(Command("removeagent"))
async def cmd_remove_agent(message: Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("🚫 Unauthorized.", parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /removeagent <telegram_id>", parse_mode="HTML")
        return

    agent_tg_id = args[1]
    async with AsyncSessionLocal() as db:
        await crud.remove_support_agent(db, agent_tg_id)
    await message.answer(f"✅ Support agent <code>{agent_tg_id}</code> removed.", parse_mode="HTML")
