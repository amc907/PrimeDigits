import os
import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from customer_bot.handlers import start, buy_number, credits, my_numbers, support

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CUSTOMER_BOT_TOKEN = os.getenv("CUSTOMER_BOT_TOKEN", "")

bot = Bot(token=CUSTOMER_BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Register routers
dp.include_router(start.router)
dp.include_router(buy_number.router)
dp.include_router(credits.router)
dp.include_router(my_numbers.router)
dp.include_router(support.router)


async def main():
    logger.info("Starting Customer Bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
