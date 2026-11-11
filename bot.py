import asyncio
import logging
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

import config
import database as db
from handlers import onboarding, materials, funnel, admin, broadcast, fallback
from scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Fail fast with an actionable message instead of starting a half-configured bot.
if not config.BOT_TOKEN or config.BOT_TOKEN == "ВАШ_ТОКЕН_ЛИД_БОТА":
    raise RuntimeError("Не задан BOT_TOKEN. Добавьте токен лид-бота в переменные окружения Amvera.")
if config.MINI_APP_URL and urlparse(config.MINI_APP_URL).scheme != "https":
    raise RuntimeError("MINI_APP_URL должен быть публичным HTTPS-адресом Amvera.")

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
# funnel — заявка на первый урок, цены, презентация школы; materials — переход в Mini App,
# admin — служебный /stats, не пересекается с остальными по командам.
dp.include_router(onboarding.router)
dp.include_router(materials.router)
dp.include_router(funnel.router)
dp.include_router(admin.router)
dp.include_router(broadcast.router)
# Последним подключается fallback, чтобы не перехватывать штатные команды и сценарии.
dp.include_router(fallback.router)


async def main():
    await db.init_db()
    scheduler = start_scheduler(bot)
    server = uvicorn.Server(uvicorn.Config(
        "miniapp:app", host=config.WEBAPP_HOST, port=config.WEBAPP_PORT,
        log_level="info", access_log=True,
    ))
    web_task = asyncio.create_task(server.serve(), name="miniapp-server")

    # Do not leave the Telegram bot polling if the Mini App HTTP server failed
    # to bind its port during startup.
    try:
        for _ in range(200):
            if server.started:
                break
            if web_task.done():
                await web_task  # propagate the startup exception
            await asyncio.sleep(0.05)
        if not server.started:
            raise RuntimeError("Mini App HTTP-сервер не запустился за 10 секунд")

        log.info("Лид-бот и Learning Space запущены; Mini App port=%s", config.WEBAPP_PORT)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        server.should_exit = True
        await web_task



if __name__ == "__main__":
    asyncio.run(main())
