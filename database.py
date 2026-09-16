"""
Хранилище состояния пользователей лид-бота.

Зачем вообще база, если материалов мало? Потому что воронка растянута
во времени (порции выдаются с задержкой в часы/дни), и после перезапуска
бота (деплой, падение процесса и т.п.) прогресс каждого пользователя должен
сохраниться — иначе человек либо получит всё заново, либо выпадет из сценария.

SQLite выбран потому что бот живёт в одном процессе (polling), это самый
простой вариант "из коробки" без внешней БД. Если бот вырастет до вебхука
на нескольких инстансах — на этом месте потребуется Postgres, но для
лид-магнита с текущим объёмом это избыточно.
"""

import datetime as dt
from typing import Optional

import aiosqlite

from config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    goal TEXT,                     -- self | work | series | NULL (не выбрал)
    level TEXT,                    -- A1 | A2 | B1 | NULL
    level_source TEXT,             -- quiz | manual
    stage TEXT DEFAULT 'new',      -- new -> onboarded -> portion1..3_sent -> nurtured
    portions_sent INTEGER DEFAULT 0,
    followups_sent INTEGER DEFAULT 0,
    last_portion_at TEXT,          -- ISO-время последней отправленной порции/чек-ина
    trial_requested INTEGER DEFAULT 0,
    waitlist_joined INTEGER DEFAULT 0,
    contact_info TEXT,
    created_at TEXT
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_SCHEMA)
        await db.commit()


def _now() -> str:
    return dt.datetime.utcnow().isoformat()


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_user_if_missing(user_id: int, username: str, first_name: str) -> dict:
    user = await get_user(user_id)
    if user:
        return user
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, username, first_name, stage, created_at) "
            "VALUES (?, ?, ?, 'new', ?)",
            (user_id, username, first_name, _now()),
        )
        await db.commit()
    return await get_user(user_id)


async def update_user(user_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {cols} WHERE user_id = ?", values)
        await db.commit()


async def set_portion_sent(user_id: int, stage: str, portions_sent: int) -> None:
    await update_user(
        user_id,
        stage=stage,
        portions_sent=portions_sent,
        last_portion_at=_now(),
    )


async def set_followup_sent(user_id: int, followups_sent: int, stage: str = None) -> None:
    fields = {"followups_sent": followups_sent, "last_portion_at": _now()}
    if stage:
        fields["stage"] = stage
    await update_user(user_id, **fields)


async def users_due_for_portion2(delay_hours: float) -> list[dict]:
    return await _users_due("portion1_sent", delay_hours)


async def users_due_for_portion3(delay_hours: float) -> list[dict]:
    return await _users_due("portion2_sent", delay_hours)


async def users_due_for_followup(delay_hours: float, max_followups: int) -> list[dict]:
    cutoff = (dt.datetime.utcnow() - dt.timedelta(hours=delay_hours)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE stage IN ('portion3_sent', 'nurtured') "
            "AND followups_sent < ? AND last_portion_at <= ?",
            (max_followups, cutoff),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def _users_due(stage: str, delay_hours: float) -> list[dict]:
    cutoff = (dt.datetime.utcnow() - dt.timedelta(hours=delay_hours)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE stage = ? AND last_portion_at <= ?",
            (stage, cutoff),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
