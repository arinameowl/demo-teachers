import os

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import config
import database as db

router = Router()

STAGE_LABELS = [
    ("new", "Начали знакомство с ботом"),
    ("onboarded", "Определили уровень и получили подборку"),
    ("learning_space_opened", "Открыли Learning Space"),
    ("nurtured", "Получили follow-up после приложения"),
    ("trial_requested", "Оставили заявку на первый урок"),
]


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        # Молчим, а не отвечаем "нет доступа" — чтобы не палить, что команда вообще существует.
        return

    stats = await db.get_funnel_stats()
    by_stage = stats["by_stage"]

    raw = config.MANAGER_CHAT_ID
    if not raw:
        manager_status = "❌ НЕ задан (заявки менеджеру не уходят!)"
    else:
        # Показываем значение частично скрытым — чтобы свериться с тем,
        # что реально введено в Railway, не спалив id целиком в чат.
        masked = raw[:3] + "…" + raw[-2:] if len(raw) > 5 else raw
        manager_status = f"✅ задан, значение: {masked} (длина: {len(raw)})"

    # Диагностика на случай опечатки/лишнего пробела в имени переменной:
    # показываем ВСЕ переменные окружения, в имени которых есть "MANAGER"
    # (даже если config.py их не подхватил).
    found_keys = [k for k in os.environ if "MANAGER" in k.upper()]
    debug_line = f"🔍 Переменные с 'MANAGER' в имени: {found_keys or 'ни одной не найдено'}"

    lines = [
        f"👥 <b>Всего зашло в бота:</b> {stats['total']} (сегодня: {stats['today']})",
        f"⚙️ <b>MANAGER_CHAT_ID:</b> {manager_status}",
        debug_line,
        "",
        "<b>По этапам воронки:</b>",
    ]
    for stage_key, label in STAGE_LABELS:
        lines.append(f"• {label}: {by_stage.get(stage_key, 0)}")

    lines += [
        "",
        f"💬 <b>Заявок на пробный урок:</b> {stats['trials']}",
        f"🎬 <b>В листе ожидания курса:</b> {stats['waitlist']}",
    ]

    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("days"))
async def cmd_days(message: Message, command: CommandObject):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    days = int(command.args) if command.args and command.args.isdigit() else 14
    days = min(days, 90)
    rows = await db.get_daily_stats(days)

    lines = [f"<b>Новые пользователи по дням (МСК), последние {days} дн.</b>", "<pre>",
             "Дата        Новых  App  Упр  Проб"]
    for r in rows:
        lines.append(f"{r['day']} {r['new_users']:>6} {r['app_opened']:>4} {r.get('exercised', 0):>4} {r['trials']:>5}")
    lines.append(f"Итого      {sum(r['new_users'] for r in rows):>6} "
                 f"{sum(r['app_opened'] for r in rows):>4} {sum(r.get('exercised', 0) for r in rows):>4} {sum(r['trials'] for r in rows):>5}")
    lines.append("</pre>")
    lines.append("Новых = /start; App = открыли Learning Space; Упр = завершили упражнение; Проб = оставили заявку.")
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("sources"))
async def cmd_sources(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    rows = await db.get_source_stats()
    lines = ["<b>Источники трафика</b>", "<pre>", "Источник              Всего App  Цены Проб"]
    for r in rows:
        lines.append(f"{r['src'][:20]:<20} {r['users']:>6} {r['app_opened']:>3} {r.get('prices_viewed', 0):>4} {r['trials']:>5}")
    lines.append("</pre>")
    a = await db.get_activity_summary()
    lines.append(f"Активны за 7 дней: {a['active_7d']}\nЗаблокировали бота: {a['blocked']}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("funnel"))
async def cmd_funnel(message: Message, command: CommandObject):
    """Подробная аналитика уникальных пользователей по событиям за период."""
    if message.from_user.id not in config.ADMIN_IDS:
        return
    days = int(command.args) if command.args and command.args.isdigit() else 30
    days = max(1, min(days, 90))
    data = await db.get_funnel_conversion(days)
    events = data["events"]
    labels = [
        ("start", "Запустили бота"),
        ("goal_selected", "Выбрали цель"),
        ("level_selected", "Определили уровень"),
        ("school_info_viewed", "Изучили информацию о школе"),
        ("prices_viewed", "Посмотрели цены"),
        ("learning_space_opened", "Открыли Learning Space"),
        ("material_opened", "Открыли материал"),
        ("book_opened", "Открыли книгу"),
        ("media_opened", "Открыли аудио или видео"),
        ("exercise_started", "Начали упражнение"),
        ("exercise_submitted", "Отправили ответы"),
        ("miniapp_exercise_completed", "Завершили упражнение на 100%"),
        ("trial_cta_clicked", "Нажали запись на первый урок"),
        ("trial_contact_submitted", "Отправили контакт"),
        ("trial_contact_cancelled", "Отменили до отправки контакта"),
        ("trial_contact_abandoned", "Не завершили отправку контакта"),
        ("trial_request_cancelled", "Отменили отправленную заявку"),
        ("trial_recovery_1_sent", "Получили recovery №1"),
        ("trial_recovery_2_sent", "Получили recovery №2"),
        ("objections_menu_opened", "Открыли меню возражений"),
        ("objection_selected", "Выбрали возражение"),
        ("manager_contact_requested", "Запросили контакт менеджера"),
    ]
    lines = [f"<b>Воронка The Teachers · последние {days} дн.</b>", "<pre>", "Этап                         Людей"]
    for key, label in labels:
        count = events.get(key, {}).get("users", 0)
        lines.append(f"{label[:27]:<27} {count:>6}")
    lines.append("</pre>")
    cohort = data["cohort"]
    users = cohort.get("users") or 0
    trials = cohort.get("trials") or 0
    conversion = (trials / users * 100) if users else 0
    lines.append(f"Новая когорта: {users} пользователей · заявок {trials} · конверсия {conversion:.1f}%")
    lines.append(f"Отписались: {cohort.get('unsubscribed') or 0} · заблокировали: {cohort.get('blocked') or 0}")

    objections = await db.get_objection_stats(days)
    if objections:
        objection_labels = {
            "format": "Формат обучения",
            "level": "Уровень",
            "speaking": "Страх говорить",
            "time": "Сроки обучения",
            "teacher": "Знакомство с преподавателем",
            "value": "Ценность индивидуальных занятий",
        }
        lines += ["", "<b>Какие возражения выбирают чаще:</b>"]
        for item in objections:
            label = objection_labels.get(item.get("objection"), item.get("objection") or "Не указано")
            lines.append(f"• {label}: {item['users']} чел. · {item['events']} выборов")

    lines.append("\nПоказатели — уникальные пользователи за период; повторные открытия не увеличивают число людей.")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("materials_stats"))
async def cmd_materials_stats(message: Message, command: CommandObject):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    days = int(command.args) if command.args and command.args.isdigit() else 30
    days = max(1, min(days, 90))
    rows = await db.get_material_stats(days)
    if not rows:
        await message.answer(f"За последние {days} дн. событий по материалам пока нет.")
        return
    labels = {"material_opened":"Открыли материал", "book_opened":"Открыли книгу", "media_opened":"Открыли аудио/видео", "exercise_started":"Начали упражнение", "exercise_submitted":"Отправили ответы", "miniapp_exercise_completed":"Завершили на 100%"}
    lines = [f"<b>Вовлечённость в Learning Space · {days} дн.</b>", "<pre>", "Событие                 Детали          Людей"]
    for row in rows:
        lines.append(f"{labels.get(row['event_name'], row['event_name']):<23} {(row.get('event_data') or '—')[:14]:<14} {row['users']:>5}")
    lines.append("</pre>")
    lines.append("Учитываются уникальные пользователи в каждой комбинации события и материала.")
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("dbcheck"))
async def cmd_dbcheck(message: Message):
    """Read-only SQLite diagnostics for authorized admins."""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    from pathlib import Path
    import sqlite3

    db_path = Path(config.DB_PATH).expanduser().resolve()
    if not db_path.is_file():
        await message.answer(
            "🗄 <b>Проверка базы данных</b>\n"
            f"Путь: <code>{db_path}</code>\n"
            "❌ Файл базы данных по этому пути не найден.\n"
            "Проверка выполнена без создания или изменения файла.",
            parse_mode="HTML",
        )
        return

    try:
        uri = db_path.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            counts = {}
            for table in ("users", "broadcasts", "broadcast_log"):
                if table in tables:
                    counts[table] = conn.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]

        lines = [
            "🗄 <b>Проверка базы данных</b>",
            f"Путь: <code>{db_path}</code>",
            f"Размер: {db_path.stat().st_size:,} байт",
            f"Таблицы: {', '.join(sorted(tables)) or 'не найдены'}",
            "",
            "<b>Количество записей:</b>",
            f"• users: {counts.get('users', 'таблица отсутствует')}",
            f"• broadcasts: {counts.get('broadcasts', 'таблица отсутствует')}",
            f"• broadcast_log: {counts.get('broadcast_log', 'таблица отсутствует')}",
            "",
            f"SQLite quick_check: <b>{integrity}</b>",
            "Режим: только чтение, данные не изменялись.",
        ]
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Database diagnostics failed")
        await message.answer(
            "❌ Не удалось прочитать базу данных. Подробности записаны в лог.",
        )

