"""SQLite persistence for The Teachers Learning Space.

User profiles, funnel events, one-time follow-ups and learning progress survive
application restarts and deployments.
"""

import datetime as dt
from pathlib import Path
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
    stage TEXT DEFAULT 'new',      -- new -> onboarded -> learning_space_opened -> nurtured / trial_requested
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
CREATE TABLE IF NOT EXISTS funnel_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_name TEXT NOT NULL,
    event_data TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_funnel_events_user ON funnel_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_funnel_events_name_date ON funnel_events(event_name, created_at);
"""


async def init_db() -> None:
    # Make custom local DB_PATH values usable while keeping Amvera's /data mount.
    Path(DB_PATH).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_SCHEMA)
        for ddl in _MIGRATIONS:
            try:
                await db.execute(ddl)
            except Exception:
                pass
        await db.executescript(_BROADCAST_SCHEMA)
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS learning_progress (
            user_id INTEGER NOT NULL,
            language TEXT NOT NULL,
            material_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('started', 'completed')),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, language, material_id)
        );
        CREATE INDEX IF NOT EXISTS idx_learning_progress_user ON learning_progress(user_id, language);
        """)
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


async def log_funnel_event(user_id: int, event_name: str, event_data: str = "") -> None:
    """Сохраняет отдельное событие воронки: просмотр цены не равен заявке."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO funnel_events (user_id, event_name, event_data, created_at) VALUES (?, ?, ?, ?)",
            (user_id, event_name, event_data, _now()),
        )
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

async def users_due_for_segment_followup(source_event: str, sent_event: str, delay_hours: float,
                                         require_no_learning_activity: bool = False) -> list[dict]:
    """Return eligible users for a single contextual follow-up segment.

    A follow-up is sent once per segment, only after the latest source event,
    and is suppressed after a trial CTA/contact request, opt-out or block.
    """
    now = dt.datetime.utcnow()
    cutoff = (now - dt.timedelta(hours=delay_hours)).isoformat()
    cooldown_cutoff = (now - dt.timedelta(hours=24)).isoformat()
    activity_clause = ""
    if require_no_learning_activity:
        activity_clause = """
          AND NOT EXISTS (
              SELECT 1 FROM funnel_events activity
              WHERE activity.user_id = u.user_id
                AND activity.event_name IN ('miniapp_progress', 'miniapp_exercise_completed', 'material_opened', 'book_opened', 'media_opened', 'exercise_started', 'exercise_submitted')
                AND datetime(activity.created_at) >= datetime(source.created_at)
          )
        """
    query = f"""
        SELECT u.* FROM users u
        JOIN funnel_events source ON source.user_id = u.user_id
          AND source.event_name = ?
        WHERE source.created_at = (
            SELECT MAX(s.created_at) FROM funnel_events s
            WHERE s.user_id = u.user_id AND s.event_name = ?
        )
          AND datetime(source.created_at) <= datetime(?)
          AND COALESCE(u.trial_requested, 0) = 0
          AND COALESCE(u.unsubscribed, 0) = 0
          AND COALESCE(u.blocked, 0) = 0
          AND NOT EXISTS (
              SELECT 1 FROM funnel_events intent
              WHERE intent.user_id = u.user_id
                AND intent.event_name IN ('trial_cta_clicked', 'trial_contact_submitted', 'manager_contact_requested')
                AND datetime(intent.created_at) >= datetime(source.created_at)
          )
          AND NOT EXISTS (
              SELECT 1 FROM funnel_events intent_after_level
              WHERE intent_after_level.user_id = u.user_id
                AND intent_after_level.event_name = 'trial_cta_clicked'
                AND datetime(intent_after_level.created_at) >= datetime((
                    SELECT MAX(level_event.created_at) FROM funnel_events level_event
                    WHERE level_event.user_id = u.user_id AND level_event.event_name = 'level_selected'
                ))
          )
          AND NOT EXISTS (
              SELECT 1 FROM funnel_events sent
              WHERE sent.user_id = u.user_id AND sent.event_name = ?
                AND datetime(sent.created_at) >= datetime(source.created_at)
          )
          AND NOT EXISTS (
              SELECT 1 FROM funnel_events recent_followup
              WHERE recent_followup.user_id = u.user_id
                AND recent_followup.event_name IN (
                    'followup_no_activity_sent',
                    'followup_after_exercise_sent',
                    'followup_after_prices_sent',
                    'nurture_day1_sent',
                    'nurture_day2_sent',
                    'nurture_day3_sent',
                    'trial_recovery_1_sent',
                    'trial_recovery_2_sent',
                    'learning_space_feedback_sent'
                )
                AND datetime(recent_followup.created_at) >= datetime(?)
          )
          {activity_clause}
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(query, (source_event, source_event, cutoff, sent_event, cooldown_cutoff))
        return [dict(row) for row in await cur.fetchall()]



async def users_due_for_learning_space_feedback(delay_hours: float = 3) -> list[dict]:
    """Users who opened Learning Space and are due a feedback check-in."""
    cutoff = (dt.datetime.utcnow() - dt.timedelta(hours=delay_hours)).isoformat()
    cooldown_cutoff = (dt.datetime.utcnow() - dt.timedelta(hours=24)).isoformat()
    query = """
        SELECT u.* FROM users u
        JOIN funnel_events source ON source.user_id = u.user_id
          AND source.event_name = 'learning_space_opened'
        WHERE source.created_at = (
            SELECT MAX(s.created_at) FROM funnel_events s
            WHERE s.user_id = u.user_id AND s.event_name = 'learning_space_opened'
        )
          AND datetime(source.created_at) <= datetime(?)
          AND COALESCE(u.trial_requested, 0) = 0
          AND COALESCE(u.awaiting_contact, 0) = 0
          AND COALESCE(u.unsubscribed, 0) = 0
          AND COALESCE(u.blocked, 0) = 0
          AND NOT EXISTS (
              SELECT 1 FROM funnel_events intent
              WHERE intent.user_id = u.user_id
                AND intent.event_name IN ('trial_cta_clicked', 'trial_contact_submitted', 'manager_contact_requested')
                AND datetime(intent.created_at) >= datetime(source.created_at)
          )
          AND NOT EXISTS (
              SELECT 1 FROM funnel_events sent
              WHERE sent.user_id = u.user_id
                AND sent.event_name = 'learning_space_feedback_sent'
                AND datetime(sent.created_at) >= datetime(source.created_at)
          )
          AND NOT EXISTS (
              SELECT 1 FROM funnel_events recent_auto
              WHERE recent_auto.user_id = u.user_id
                AND recent_auto.event_name IN (
                    'followup_no_activity_sent', 'followup_after_exercise_sent',
                    'followup_after_prices_sent', 'learning_space_feedback_sent',
                    'nurture_day1_sent', 'nurture_day2_sent', 'nurture_day3_sent',
                    'trial_recovery_1_sent', 'trial_recovery_2_sent'
                )
                AND datetime(recent_auto.created_at) >= datetime(?)
          )
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(query, (cutoff, cooldown_cutoff))
        return [dict(row) for row in await cur.fetchall()]

async def get_due_nurture_actions(day1_delay_hours: float = 4) -> list[dict]:
    """Return at most one due three-day nurture action per user."""
    now = dt.datetime.utcnow()
    cooldown = now - dt.timedelta(hours=24)
    def parse_time(value):
        if not value:
            return None
        try:
            return dt.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    actions = []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT u.*,
                   (SELECT e.created_at FROM funnel_events e
                    WHERE e.user_id=u.user_id AND e.event_name='level_selected'
                    ORDER BY e.id DESC LIMIT 1) AS level_at
            FROM users u
            WHERE u.level IN ('A1','A2','B1')
              AND COALESCE(u.trial_requested,0)=0
              AND COALESCE(u.awaiting_contact,0)=0
              AND COALESCE(u.unsubscribed,0)=0
              AND COALESCE(u.blocked,0)=0
        """)
        users = [dict(row) for row in await cur.fetchall()]

        for user in users:
            level_at = parse_time(user.get("level_at"))
            if not level_at:
                continue
            cur = await conn.execute("""
                SELECT event_name, created_at FROM funnel_events
                WHERE user_id=? AND datetime(created_at)>=datetime(?)
                ORDER BY id
            """, (user["user_id"], level_at.isoformat()))
            events = [dict(row) for row in await cur.fetchall()]
            event_times = {}
            for event in events:
                event_times.setdefault(event["event_name"], []).append(parse_time(event["created_at"]))

            if (event_times.get("trial_cta_clicked") or event_times.get("trial_contact_submitted")
                    or event_times.get("manager_contact_requested")):
                continue

            cur = await conn.execute(
                "SELECT created_at FROM funnel_events WHERE user_id=? "
                "AND event_name IN ('followup_no_activity_sent','followup_after_exercise_sent',"
                "'followup_after_prices_sent','nurture_day1_sent','nurture_day2_sent','nurture_day3_sent',"
                "'trial_recovery_1_sent','trial_recovery_2_sent','learning_space_feedback_sent') "
                "AND datetime(created_at)>=datetime(?)",
                (user["user_id"], cooldown.isoformat()),
            )
            recent_auto_times = [parse_time(row["created_at"]) for row in await cur.fetchall()]
            latest_auto = max((value for value in recent_auto_times if value), default=None)
            has_recent_auto = bool(latest_auto and latest_auto >= cooldown)

            day1_sent = bool(event_times.get("nurture_day1_sent"))
            day1_skipped = bool(event_times.get("nurture_day1_skipped"))
            day2_sent = bool(event_times.get("nurture_day2_sent"))
            day3_sent = bool(event_times.get("nurture_day3_sent"))

            if not day1_sent and not day1_skipped:
                if now - level_at < dt.timedelta(hours=day1_delay_hours):
                    continue
                if event_times.get("learning_space_opened"):
                    actions.append({"user_id": user["user_id"], "action": "day1_skip"})
                elif not has_recent_auto:
                    actions.append({"user_id": user["user_id"], "action": "day1"})
                continue

            if not day2_sent:
                day1_times = (
                    event_times.get("nurture_day1_sent", [])
                    or event_times.get("nurture_day1_skipped", [])
                    or [level_at]
                )
                day1_time = max(day1_times)
                if now - day1_time < dt.timedelta(hours=24):
                    continue
                if not has_recent_auto:
                    completed = bool(event_times.get("miniapp_exercise_completed"))
                    actions.append({
                        "user_id": user["user_id"],
                        "action": "day2_after_exercise" if completed else "day2",
                    })
                continue

            if not day3_sent:
                day2_times = event_times.get("nurture_day2_sent", [])
                day2_time = max(day2_times) if day2_times else None
                if day2_time and now - day2_time >= dt.timedelta(hours=24) and not has_recent_auto:
                    actions.append({"user_id": user["user_id"], "action": "day3"})

    return actions



async def get_due_trial_recovery_actions(first_delay_minutes: int = 45) -> list[dict]:
    """Find abandoned or cancelled trial-contact requests for two limited reminders."""
    now = dt.datetime.utcnow()
    cooldown = now - dt.timedelta(hours=24)

    def parse_time(value):
        if not value:
            return None
        try:
            return dt.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    actions = []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT u.*,
                   (SELECT e.created_at FROM funnel_events e
                    WHERE e.user_id=u.user_id AND e.event_name='trial_cta_clicked'
                    ORDER BY e.id DESC LIMIT 1) AS latest_trial_cta
            FROM users u
            WHERE COALESCE(u.trial_requested,0)=0
              AND COALESCE(u.unsubscribed,0)=0
              AND COALESCE(u.blocked,0)=0
        """)
        users = [dict(row) for row in await cur.fetchall()]

        for user in users:
            cta_at = parse_time(user.get("latest_trial_cta"))
            if not cta_at or now - cta_at < dt.timedelta(minutes=first_delay_minutes):
                continue

            cur = await conn.execute("""
                SELECT event_name, created_at FROM funnel_events
                WHERE user_id=? AND datetime(created_at)>=datetime(?)
                ORDER BY id
            """, (user["user_id"], cta_at.isoformat()))
            events = [dict(row) for row in await cur.fetchall()]
            names = [event["event_name"] for event in events]

            # Не напоминаем тем, кто явно отменил ввод контакта или уже
            # отменил отправленную заявку: это осознанное действие, а не брошенная форма.
            if any(name in names for name in (
                "trial_contact_submitted",
                "trial_contact_cancelled",
                "trial_request_cancelled",
                "manager_contact_requested",
            )):
                continue

            first_sent = [
                parse_time(event["created_at"]) for event in events
                if event["event_name"] == "trial_recovery_1_sent"
            ]
            second_sent = "trial_recovery_2_sent" in names

            cur = await conn.execute(
                "SELECT created_at FROM funnel_events WHERE user_id=? "
                "AND event_name IN ('followup_no_activity_sent','followup_after_exercise_sent',"
                "'followup_after_prices_sent','nurture_day1_sent','nurture_day2_sent','nurture_day3_sent',"
                "'trial_recovery_1_sent','trial_recovery_2_sent') "
                "AND datetime(created_at)>=datetime(?)",
                (user["user_id"], cooldown.isoformat()),
            )
            recent = [parse_time(row["created_at"]) for row in await cur.fetchall()]
            if any(value and value >= cooldown for value in recent):
                continue

            if not first_sent:
                # The contact form may have been left open or explicitly cancelled.
                if user.get("awaiting_contact"):
                    await conn.execute(
                        "UPDATE users SET awaiting_contact=0 WHERE user_id=?",
                        (user["user_id"],),
                    )
                    await conn.commit()
                    await conn.execute(
                        "INSERT INTO funnel_events (user_id,event_name,event_data,created_at) VALUES (?,?,?,?)",
                        (user["user_id"], "trial_contact_abandoned", "", now.isoformat()),
                    )
                    await conn.commit()
                actions.append({"user_id": user["user_id"], "action": "recovery_1"})
            elif not second_sent:
                first_at = max(value for value in first_sent if value)
                if now - first_at >= dt.timedelta(hours=24):
                    actions.append({"user_id": user["user_id"], "action": "recovery_2"})

    return actions


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
            "SELECT COUNT(*) AS c FROM users WHERE date(created_at, '+3 hours') = date('now', '+3 hours')"
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
    """Дневная когорта: новые пользователи, открытия приложения, упражнения и заявки (МСК)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT date(u.created_at, '+3 hours') AS day,
                   COUNT(*) AS new_users,
                   SUM(CASE WHEN EXISTS (SELECT 1 FROM funnel_events e WHERE e.user_id=u.user_id AND e.event_name='learning_space_opened') THEN 1 ELSE 0 END) AS app_opened,
                   SUM(CASE WHEN EXISTS (SELECT 1 FROM funnel_events e WHERE e.user_id=u.user_id AND e.event_name='miniapp_exercise_completed') THEN 1 ELSE 0 END) AS exercised,
                   SUM(CASE WHEN u.trial_requested=1 THEN 1 ELSE 0 END) AS trials
            FROM users u
            WHERE date(u.created_at, '+3 hours') >= date('now', '+3 hours', ?)
            GROUP BY day ORDER BY day DESC
            """, (f"-{days - 1} days",)
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


# ---------- Расширенная аналитика воронки ----------

async def get_funnel_conversion(days: int = 30) -> dict:
    """Уникальные пользователи по ключевым событиям за период (МСК)."""
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT event_name, COUNT(DISTINCT user_id) AS users, COUNT(*) AS events "
            "FROM funnel_events WHERE datetime(created_at) >= datetime(?) GROUP BY event_name", (cutoff,)
        )
        raw = {r["event_name"]: {"users": r["users"], "events": r["events"]} for r in await cur.fetchall()}
        cur = await conn.execute(
            "SELECT COUNT(*) AS users, "
            "SUM(CASE WHEN trial_requested=1 THEN 1 ELSE 0 END) AS trials, "
            "SUM(CASE WHEN unsubscribed=1 THEN 1 ELSE 0 END) AS unsubscribed, "
            "SUM(CASE WHEN blocked=1 THEN 1 ELSE 0 END) AS blocked "
            "FROM users WHERE datetime(created_at) >= datetime(?)", (cutoff,)
        )
        cohort = dict(await cur.fetchone())
    return {"days": days, "events": raw, "cohort": cohort}


async def get_objection_stats(days: int = 30) -> list[dict]:
    """Count objection selections by key for the requested period."""
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT event_data AS objection, COUNT(DISTINCT user_id) AS users, COUNT(*) AS events "
            "FROM funnel_events WHERE event_name='objection_selected' "
            "AND datetime(created_at) >= datetime(?) "
            "GROUP BY event_data ORDER BY users DESC, events DESC",
            (cutoff,),
        )
        return [dict(row) for row in await cur.fetchall()]


async def get_material_stats(days: int = 30) -> list[dict]:
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT event_name, event_data, COUNT(DISTINCT user_id) AS users, COUNT(*) AS events "
            "FROM funnel_events WHERE datetime(created_at) >= datetime(?) "
            "AND event_name IN ('material_opened','book_opened','media_opened','exercise_started','exercise_submitted','miniapp_exercise_completed') "
            "GROUP BY event_name, event_data ORDER BY users DESC", (cutoff,)
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_source_stats() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT COALESCE(u.source, 'до трекинга') AS src,
                   COUNT(*) AS users,
                   SUM(CASE WHEN EXISTS (SELECT 1 FROM funnel_events e WHERE e.user_id=u.user_id AND e.event_name='learning_space_opened') THEN 1 ELSE 0 END) AS app_opened,
                   SUM(CASE WHEN EXISTS (SELECT 1 FROM funnel_events e WHERE e.user_id=u.user_id AND e.event_name='prices_viewed') THEN 1 ELSE 0 END) AS prices_viewed,
                   SUM(CASE WHEN u.trial_requested=1 THEN 1 ELSE 0 END) AS trials
            FROM users u GROUP BY src ORDER BY users DESC
            """
        )
        return [dict(r) for r in await cur.fetchall()]


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
