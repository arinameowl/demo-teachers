"""
Дублирование заявок на пробный урок в Google-таблицу.

Работает через веб-приложение Google Apps Script (без сервисных аккаунтов и
дополнительных библиотек: aiohttp уже входит в зависимости aiogram).

Настройки — переменные окружения (в Амвере):
  SHEETS_WEBHOOK_URL — адрес веб-приложения (заканчивается на /exec)
  SHEETS_SECRET      — тот же пароль, что указан в скрипте таблицы

Если SHEETS_WEBHOOK_URL не задан, функция просто ничего не делает.
Любая ошибка только логируется: заявка всё равно сохраняется в базе
и уходит менеджеру.
"""

import datetime as dt
import logging
import os

import aiohttp

import texts

log = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL", "").strip()
SECRET = os.environ.get("SHEETS_SECRET", "").strip()


def _msk_now() -> str:
    return (dt.datetime.utcnow() + dt.timedelta(hours=3)).strftime("%d.%m.%Y %H:%M")


async def append_trial_row(
    *,
    name: str,
    username: str | None,
    user_id: int,
    contact: str,
    level: str | None,
    goal: str | None,
    source: str | None,
) -> bool:
    """Добавляет новую строку в таблицу. Возвращает True, если запись прошла."""
    if not WEBHOOK_URL:
        return False

    row = [
        _msk_now(),
        name or "—",
        f"@{username}" if username else "—",
        str(user_id),
        contact or "—",
        level or "—",
        texts.GOAL_LABELS.get(goal, "—") if goal else "—",
        source or "—",
    ]
    payload = {"secret": SECRET, "row": row}

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(WEBHOOK_URL, json=payload) as resp:
                body = await resp.text()
        compact = body.replace(" ", "")
        if resp.status != 200 or '"ok":true' not in compact:
            log.error("Google-таблица не приняла заявку: HTTP %s, ответ: %s", resp.status, body[:300])
            return False
        return True
    except Exception:
        log.exception("Не удалось записать заявку в Google-таблицу")
        return False
