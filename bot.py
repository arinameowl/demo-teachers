import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from handlers import onboarding, materials, funnel
from scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Порядок важен: онбординг обрабатывает /start и квиз-коллбэки,
# funnel — команды меню (/trial, /course...), materials — /materials и порции.
dp.include_router(onboarding.router)
dp.include_router(materials.router)
dp.include_router(funnel.router)


async def main():
    await db.init_db()
    start_scheduler(bot)
    log.info("Лид-бот запущен, начинаю polling")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
