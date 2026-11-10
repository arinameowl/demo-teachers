"""
Дублирование заявок на пробный урок в Google-таблицу.

Порядок столбцов фиксирован под таблицу заявок:
A — дата, B — источник ("Бот"), C — имя, D — Telegram username,
E — язык (пока пусто до внедрения выбора языка), F-H — данные пробного урока,
I — статус ("В работе"), J — комментарий.

Настройки — переменные окружения (в Амвере):
  SHEETS_WEBHOOK_URL — адрес веб-приложения (заканчивается на /exec)
  SHEETS_SECRET      — тот же пароль, что указан в скрипте таблицы
"""

import datetime as dt
import logging
import os

import aiohttp

log = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL", "").strip()
SECRET = os.environ.get("SHEETS_SECRET", "").strip()


def _msk_now() -> str:
    return (dt.datetime.utcnow() + dt.timedelta(hours=3)).strftime("%d.%m.%Y %H:%M")


def _build_trial_row(*, name: str, username: str | None) -> list[str]:
    """Формирует строку строго по колонкам A:J текущей Google-таблицы."""
    return [
        _msk_now(),                         # A: Дата
        "Бот",                              # B: Источник
        name or "—",                        # C: Имя
        f"@{username}" if username else "—",# D: Ник ТГ
        "",                                 # E: Язык — подключим после выбора языка в боте
        "",                                 # F: Пробный
        "",                                 # G: Дата пробного
        "",                                 # H: Преподаватель
        "В работе",                         # I: Статус
        "",                                 # J: Комментарий
    ]


async def append_trial_row(*, name: str, username: str | None) -> bool:
    """Добавляет заявку в Google-таблицу. Возвращает True, если запись прошла."""
    if not WEBHOOK_URL:
        log.warning("Google-таблица не настроена: SHEETS_WEBHOOK_URL не задан")
        return False

    payload = {"secret": SECRET, "row": _build_trial_row(name=name, username=username)}

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(WEBHOOK_URL, json=payload) as resp:
                body = await resp.text()
                status = resp.status
        compact = body.replace(" ", "")
        if status != 200 or '"ok":true' not in compact:
            log.error("Google-таблица не приняла заявку: HTTP %s, ответ: %s", status, body[:300])
            return False
        return True
    except Exception:
        log.exception("Не удалось записать заявку в Google-таблицу")
        return False
