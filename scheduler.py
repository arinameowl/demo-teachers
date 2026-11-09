"""Contextual follow-ups and the three-day nurture sequence."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
import keyboards as kb
import texts

log = logging.getLogger(__name__)


def _is_quiet_hours() -> bool:
    hour = datetime.now(ZoneInfo("Europe/Moscow")).hour
    return hour < 10 or hour >= 20


async def _send_segment(bot: Bot, source_event: str, sent_event: str, delay: float, text: str,
                        require_no_learning_activity: bool = False) -> None:
    users = await db.users_due_for_segment_followup(
        source_event, sent_event, delay, require_no_learning_activity
    )
    for user in users:
        user_id = user["user_id"]
        try:
            await bot.send_message(user_id, text, reply_markup=kb.contextual_followup_keyboard())
            await db.log_funnel_event(user_id, sent_event)
            await db.update_user(user_id, stage="nurtured")
            log.info("Follow-up %s sent to user %s", sent_event, user_id)
        except TelegramForbiddenError:
            await db.update_user(user_id, blocked=1)
        except Exception:
            log.exception("Не удалось отправить follow-up %s пользователю %s", sent_event, user_id)


async def _send_learning_space_feedback(bot: Bot) -> None:
    users = await db.users_due_for_learning_space_feedback(
        config.LEARNING_SPACE_FEEDBACK_HOURS
    )
    log.info("Learning Space feedback: eligible users=%s", len(users))
    for user in users:
        user_id = user["user_id"]
        try:
            await bot.send_message(
                user_id,
                texts.LEARNING_SPACE_FEEDBACK,
                reply_markup=kb.contextual_followup_keyboard(),
            )
            await db.log_funnel_event(user_id, "learning_space_feedback_sent")
            log.info("Learning Space feedback sent to user %s", user_id)
        except TelegramForbiddenError:
            await db.update_user(user_id, blocked=1)
        except Exception:
            log.exception("Не удалось отправить Learning Space feedback пользователю %s", user_id)

async def _send_nurture(bot: Bot) -> None:
    actions = await db.get_due_nurture_actions()
    messages = {
        "day1": ("nurture_day1_sent", texts.NURTURE_DAY1, kb.nurture_learning_keyboard("Открыть Learning Space")),
        "day2": ("nurture_day2_sent", texts.NURTURE_DAY2, kb.nurture_learning_keyboard("Продолжить практику")),
        "day2_after_exercise": ("nurture_day2_sent", texts.NURTURE_DAY2_AFTER_EXERCISE, kb.nurture_exercise_keyboard()),
        "day3": ("nurture_day3_sent", texts.NURTURE_DAY3, kb.nurture_day3_keyboard()),
    }
    for item in actions:
        user_id = item["user_id"]
        action = item["action"]
        if action == "day1_skip":
            await db.log_funnel_event(user_id, "nurture_day1_skipped")
            log.info("Nurture day 1 skipped: user %s already opened Learning Space", user_id)
            continue
        sent_event, message_text, reply_markup = messages[action]
        try:
            await bot.send_message(user_id, message_text, reply_markup=reply_markup)
            await db.log_funnel_event(user_id, sent_event)
            await db.update_user(user_id, stage="nurtured")
            log.info("Nurture %s sent to user %s", action, user_id)
        except TelegramForbiddenError:
            await db.update_user(user_id, blocked=1)
        except Exception:
            log.exception("Не удалось отправить nurture %s пользователю %s", action, user_id)


async def _send_trial_recovery(bot: Bot) -> None:
    actions = await db.get_due_trial_recovery_actions()
    messages = {
        "recovery_1": ("trial_recovery_1_sent", texts.TRIAL_RECOVERY_1),
        "recovery_2": ("trial_recovery_2_sent", texts.TRIAL_RECOVERY_2),
    }
    for item in actions:
        user_id = item["user_id"]
        event_name, message_text = messages[item["action"]]
        try:
            await bot.send_message(user_id, message_text, reply_markup=kb.trial_recovery_keyboard())
            await db.log_funnel_event(user_id, event_name)
            log.info("Trial recovery %s sent to user %s", item["action"], user_id)
        except TelegramForbiddenError:
            await db.update_user(user_id, blocked=1)
        except Exception:
            log.exception("Не удалось отправить trial recovery %s пользователю %s", item["action"], user_id)


async def _tick(bot: Bot) -> None:
    if _is_quiet_hours():
        log.info("Проверка воронки пропущена: тихие часы (20:00–10:00 МСК)")
        return

    jobs = (
        ("Learning Space feedback", lambda: _send_learning_space_feedback(bot)),
        ("follow-up без активности", lambda: _send_segment(
            bot, "learning_space_opened", "followup_no_activity_sent",
            config.FOLLOWUP_NO_ACTIVITY_HOURS, texts.FOLLOWUP_NO_ACTIVITY,
            require_no_learning_activity=True,
        )),
        ("follow-up после упражнения", lambda: _send_segment(
            bot, "miniapp_exercise_completed", "followup_after_exercise_sent",
            config.FOLLOWUP_AFTER_EXERCISE_HOURS, texts.FOLLOWUP_AFTER_EXERCISE,
        )),
        ("follow-up после цен", lambda: _send_segment(
            bot, "prices_viewed", "followup_after_prices_sent",
            config.FOLLOWUP_AFTER_PRICES_HOURS, texts.FOLLOWUP_AFTER_PRICES,
        )),
        ("Day 1–3", lambda: _send_nurture(bot)),
        ("восстановление записи", lambda: _send_trial_recovery(bot)),
    )
    for name, job in jobs:
        try:
            await job()
        except Exception:
            log.exception("Ошибка сценария планировщика: %s; остальные сценарии продолжат работу", name)

def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _tick, "date", args=[bot], id="funnel_initial_tick",
    )
    scheduler.add_job(
        _tick, "interval", minutes=config.SCHEDULER_INTERVAL_MINUTES,
        args=[bot], id="funnel_tick", max_instances=1, coalesce=True,
    )
    scheduler.start()
    log.info("Планировщик воронки запущен (каждые %s мин.)", config.SCHEDULER_INTERVAL_MINUTES)
    return scheduler
