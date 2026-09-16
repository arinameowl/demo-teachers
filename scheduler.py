"""
Планировщик — сердце "порционной выдачи" и "регулярности" из архитектуры.

Почему не asyncio.sleep() по пользователю: бот может перезапускаться (деплой,
падение процесса), а sleep() в таком случае просто пропадёт вместе с задачей.
Вместо этого раз в SCHEDULER_INTERVAL_MINUTES бот сам спрашивает у базы
"кому пора отправить следующий шаг" — это переживает любой рестарт, потому
что вся нужная информация (last_portion_at, stage) лежит в SQLite, а не в
памяти процесса.
"""

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
import texts
from handlers.materials import send_portion2, send_portion3

log = logging.getLogger(__name__)


async def _tick(bot: Bot) -> None:
    await _send_portion2_batch(bot)
    await _send_portion3_batch(bot)
    await _send_followup_batch(bot)


async def _send_portion2_batch(bot: Bot) -> None:
    users = await db.users_due_for_portion2(config.PORTION_2_DELAY_HOURS)
    for user in users:
        try:
            await send_portion2(bot, user["user_id"], user["level"], user.get("goal"))
        except Exception:
            log.exception("Не удалось отправить порцию 2 пользователю %s", user["user_id"])


async def _send_portion3_batch(bot: Bot) -> None:
    users = await db.users_due_for_portion3(config.PORTION_3_DELAY_HOURS)
    for user in users:
        try:
            await send_portion3(bot, user["user_id"], user["level"], user.get("goal"))
        except Exception:
            log.exception("Не удалось отправить порцию 3 пользователю %s", user["user_id"])


async def _send_followup_batch(bot: Bot) -> None:
    users = await db.users_due_for_followup(config.FOLLOWUP_DELAY_HOURS, config.MAX_FOLLOWUPS)
    for user in users:
        followups_sent = user.get("followups_sent", 0)
        try:
            msg = texts.FOLLOWUP_MESSAGES[min(followups_sent, len(texts.FOLLOWUP_MESSAGES) - 1)]
            await bot.send_message(user["user_id"], msg)
            new_count = followups_sent + 1
            stage = "nurtured" if new_count >= config.MAX_FOLLOWUPS else user["stage"]
            if new_count >= config.MAX_FOLLOWUPS:
                await bot.send_message(user["user_id"], texts.FUNNEL_SILENCE_NOTICE)
            await db.set_followup_sent(user["user_id"], new_count, stage=stage)
        except Exception:
            log.exception("Не удалось отправить чек-ин пользователю %s", user["user_id"])


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _tick,
        "interval",
        minutes=config.SCHEDULER_INTERVAL_MINUTES,
        args=[bot],
        id="funnel_tick",
    )
    scheduler.start()
    log.info("Планировщик воронки запущен (каждые %s мин.)", config.SCHEDULER_INTERVAL_MINUTES)
    return scheduler
