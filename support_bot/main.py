import os
import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from support_bot.handlers import support

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPPORT_BOT_TOKEN = os.getenv("SUPPORT_BOT_TOKEN", "")

bot = Bot(token=SUPPORT_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Register routers
dp.include_router(support.router)


async def main():
    logger.info("Starting Support Bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
