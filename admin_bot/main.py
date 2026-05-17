import os
import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from admin_bot.handlers import dashboard, users, broadcast

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")

bot = Bot(token=ADMIN_BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

dp.include_router(dashboard.router)
dp.include_router(users.router)
dp.include_router(broadcast.router)


async def main():
    logger.info("Starting Admin Bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
