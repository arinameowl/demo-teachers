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
    awaiting_contact INTEGER DEFAULT 0,
    waitlist_joined INTEGER DEFAULT 0,
    contact_info TEXT,
    created_at TEXT
);
"""

# Колонки, добавленные позже. ALTER TABLE ADD COLUMN безопасно падает,
# если колонка уже есть — эту ошибку просто игнорируем.
_MIGRATIONS = (
    "ALTER TABLE users ADD COLUMN awaiting_contact INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN source TEXT",
    "ALTER TABLE users ADD COLUMN last_active_at TEXT",
    "ALTER TABLE users ADD COLUMN trial_requested_at TEXT",
    "ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN unsubscribed INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN last_broadcast_at TEXT",
)

_BROADCAST_SCHEMA = """
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    preview TEXT,
    audience INTEGER DEFAULT 0,
    sent INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS broadcast_log (
    broadcast_id INTEGER,
    user_id INTEGER,
    clicked INTEGER DEFAULT 0,
    unsubscribed INTEGER DEFAULT 0,
    PRIMARY KEY (broadcast_id, user_id)
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_SCHEMA)
        for ddl in _MIGRATIONS:
            try:
                await db.execute(ddl)
            except Exception:
                pass
        await db.executescript(_BROADCAST_SCHEMA)
        await db.commit()


def _now() -> str:
    return dt.datetime.utcnow().isoformat()


# ---------- Пользователи ----------

async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_user_if_missing(user_id: int, username: str, first_name: str,
                                 source: str = "direct") -> dict:
    user = await get_user(user_id)
    if user:
        return user
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, username, first_name, stage, created_at, source, last_active_at) "
            "VALUES (?, ?, ?, 'new', ?, ?, ?)",
            (user_id, username, first_name, now, source, now),
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


async def touch_user(user_id: int) -> None:
    """Любое действие пользователя: обновляем активность и снимаем флаг блокировки."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_active_at = ?, blocked = 0 WHERE user_id = ?",
            (_now(), user_id),
        )
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


# ---------- Планировщик воронки ----------

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
            "AND followups_sent < ? AND last_portion_at <= ? AND COALESCE(blocked, 0) = 0",
            (max_followups, cutoff),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def _users_due(stage: str, delay_hours: float) -> list[dict]:
    cutoff = (dt.datetime.utcnow() - dt.timedelta(hours=delay_hours)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE stage = ? AND last_portion_at <= ? AND COALESCE(blocked, 0) = 0",
            (stage, cutoff),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ---------- Статистика ----------

async def get_funnel_stats() -> dict:
    """Сводка по воронке для команды /stats: сколько людей на каждом этапе,
    сколько заявок на пробный и в листе ожидания курса."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute("SELECT COUNT(*) AS c FROM users")
        total = (await cur.fetchone())["c"]

        cur = await db.execute("SELECT stage, COUNT(*) AS c FROM users GROUP BY stage")
        by_stage = {r["stage"]: r["c"] for r in await cur.fetchall()}

        cur = await db.execute("SELECT COUNT(*) AS c FROM users WHERE trial_requested = 1")
        trials = (await cur.fetchone())["c"]

        cur = await db.execute("SELECT COUNT(*) AS c FROM users WHERE waitlist_joined = 1")
        waitlist = (await cur.fetchone())["c"]

        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE date(created_at) = date('now')"
        )
        today = (await cur.fetchone())["c"]

    return {
        "total": total,
        "by_stage": by_stage,
        "trials": trials,
        "waitlist": waitlist,
        "today": today,
    }


async def get_daily_stats(days: int = 14) -> list[dict]:
    """Новые пользователи по дням (МСК) + как далеко дошли."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT date(created_at, '+3 hours') AS day,
                   COUNT(*) AS new_users,
                   SUM(CASE WHEN portions_sent >= 1 THEN 1 ELSE 0 END) AS got_p1,
                   SUM(CASE WHEN portions_sent >= 3 THEN 1 ELSE 0 END) AS got_p3,
                   COALESCE(SUM(trial_requested), 0) AS trials
            FROM users
            WHERE date(created_at, '+3 hours') >= date('now', '+3 hours', ?)
            GROUP BY day
            ORDER BY day DESC
            """,
            (f"-{days - 1} days",),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_source_stats() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT COALESCE(source, 'до трекинга') AS src,
                   COUNT(*) AS users,
                   SUM(CASE WHEN portions_sent >= 1 THEN 1 ELSE 0 END) AS got_p1,
                   COALESCE(SUM(trial_requested), 0) AS trials
            FROM users GROUP BY src ORDER BY users DESC
            """
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_activity_summary() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN date(last_active_at) >= date('now','-7 days') THEN 1 ELSE 0 END), 0) AS active_7d,
                   COALESCE(SUM(blocked), 0) AS blocked
            FROM users
            """
        )
        return dict(await cur.fetchone())


# ---------- Рассылки ----------

async def broadcast_audience(goal=None, level=None, min_gap_days: int = 6,
                             funnel_gap_hours: int = 48) -> list[int]:
    """Кому можно слать рекламную рассылку прямо сейчас (мягкие ограничения)."""
    now = dt.datetime.utcnow()
    q = (
        "SELECT user_id FROM users WHERE COALESCE(blocked,0)=0 "
        "AND COALESCE(unsubscribed,0)=0 AND COALESCE(trial_requested,0)=0 "
        "AND created_at <= ? "
        "AND (last_broadcast_at IS NULL OR last_broadcast_at <= ?) "
        "AND (last_portion_at IS NULL OR last_portion_at <= ?)"
    )
    params = [
        (now - dt.timedelta(days=3)).isoformat(),
        (now - dt.timedelta(days=min_gap_days)).isoformat(),
        (now - dt.timedelta(hours=funnel_gap_hours)).isoformat(),
    ]
    if goal:
        q += " AND goal = ?"
        params.append(goal)
    if level:
        q += " AND level = ?"
        params.append(level)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(q, params)
        return [r[0] for r in await cur.fetchall()]


async def create_broadcast(preview: str, audience: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO broadcasts (created_at, preview, audience) VALUES (?,?,?)",
            (_now(), preview[:80], audience),
        )
        await db.commit()
        return cur.lastrowid


async def log_broadcast_sent(bid: int, user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO broadcast_log (broadcast_id, user_id) VALUES (?,?)", (bid, user_id)
        )
        await db.execute("UPDATE users SET last_broadcast_at = ? WHERE user_id = ?", (_now(), user_id))
        await db.commit()


async def finish_broadcast(bid: int, sent: int, failed: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE broadcasts SET sent=?, failed=? WHERE id=?", (sent, failed, bid))
        await db.commit()


async def mark_broadcast_event(bid: int, user_id: int, field: str) -> None:
    if field not in ("clicked", "unsubscribed"):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE broadcast_log SET {field} = 1 WHERE broadcast_id = ? AND user_id = ?",
            (bid, user_id),
        )
        await db.commit()


async def get_broadcast_report(limit: int = 5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT b.id, b.created_at, b.preview, b.sent, b.failed,
                   COALESCE(SUM(l.clicked),0) AS clicks,
                   COALESCE(SUM(l.unsubscribed),0) AS unsubs
            FROM broadcasts b LEFT JOIN broadcast_log l ON l.broadcast_id = b.id
            GROUP BY b.id ORDER BY b.id DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]
