import asyncio
import logging

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from handlers import onboarding, materials, funnel, admin
from scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class ActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            try:
                await db.touch_user(user.id)
            except Exception:
                log.exception("touch_user failed")
        return await handler(event, data)


dp.message.outer_middleware(ActivityMiddleware())
dp.callback_query.outer_middleware(ActivityMiddleware())

# Порядок важен: онбординг обрабатывает /start и квиз-коллбэки,
# funnel — команды меню (/trial, /course...), materials — /materials и порции,
# admin — служебный /stats, не пересекается с остальными по командам.
dp.include_router(onboarding.router)
dp.include_router(materials.router)
dp.include_router(funnel.router)
dp.include_router(admin.router)


async def main():
    await db.init_db()
    start_scheduler(bot)
    log.info("Лид-бот запущен, начинаю polling")
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())
