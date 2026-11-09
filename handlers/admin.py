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
        "<b>Текущее состояние пользователей (не последовательная воронка):</b>",
    ]
    for stage_key, label in STAGE_LABELS:
        lines.append(f"• {label}: {by_stage.get(stage_key, 0)}")

    lines += [
        "",
        f"💬 <b>Отправлено заявок на пробный:</b> {stats['trials']} (уникальных людей: {stats['trial_people']})",
        f"📅 <b>Сегодня отправлено:</b> {stats['trials_today']} (уникальных людей: {stats['trial_people_today']})",
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
             "Дата        Новых  App  Упр  Заяв. Люди"]
    for r in rows:
        lines.append(f"{r['day']} {r['new_users']:>6} {r['app_opened']:>4} {r.get('exercised', 0):>4} {r['trials']:>5} {r.get('trial_people', 0):>4}")
    lines.append(f"Итого      {sum(r['new_users'] for r in rows):>6} "
                 f"{sum(r['app_opened'] for r in rows):>4} {sum(r.get('exercised', 0) for r in rows):>4} "
                 f"{sum(r['trials'] for r in rows):>5} {sum(r.get('trial_people', 0) for r in rows):>4}")
    lines.append("</pre>")
    lines.append("Новых = /start; App = уникальные пользователи, открывшие Learning Space в этот день; Упр = уникальные пользователи, завершившие упражнение в этот день; Заяв. = все отправки контакта (события); Люди = уникальные пользователи, отправившие контакт в этот день.")
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("sources"))
async def cmd_sources(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    rows = await db.get_source_stats()
    lines = [
        "<b>Источники трафика · накопительно</b>", "<pre>",
        "Источник           Люди  App  Цены  CTA  Заяв.Люди"
    ]
    for r in rows:
        lines.append(
            f"{r['src'][:18]:<18} {r['users']:>5} {r['app_opened']:>4} "
            f"{r['prices_viewed']:>5} {r['trial_clicked']:>4} {r['trial_people']:>6}"
        )
        lines.append(
            f"  App/база {r['app_rate']:.1f}% · люди с заявкой/база {r['trial_rate']:.1f}% "
            f"· App → заявка {r['app_to_trial_rate']:.1f}% · отправок контакта {r['trial_events']}"
        )
    lines.append("</pre>")
    activity = await db.get_activity_summary()
    lines.append(f"Активны за 7 дней: {activity['active_7d']} · заблокировали бота: {activity['blocked']}")
    lines.append("Накопительно за всё время. Люди = уникальные пользователи; CTA = уникальные нажавшие; Заяв.Люди = уникальные отправившие контакт; отправок контакта может быть больше из-за повторных заявок. App → заявка учитывает отправку контакта после открытия Learning Space. Источники без метки объединены в «до трекинга».")
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
        ("learning_space_feedback_sent", "Получили приглашение на бесплатный первый урок"),
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
    lines = [f"<b>Воронка The Teachers · последние {days} дн.</b>", "<pre>", "Этап                         Людей  Событий"]
    for key, label in labels:
        count = events.get(key, {}).get("users", 0)
        event_count = events.get(key, {}).get("events", 0)
        lines.append(f"{label[:27]:<27} {count:>6} {event_count:>8}")
    lines.append("</pre>")
    cohort = data["cohort"]
    users = cohort.get("users") or 0
    trials = cohort.get("trials") or 0
    conversion = (trials / users * 100) if users else 0
    lines.append(f"Когорта новых пользователей (регистрация за период): {users} · отправили контакт: {trials} · конверсия в отправку: {conversion:.1f}%")
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

    # Конверсии соседних этапов считаем по уникальным пользователям периода.
    lines += ["", "<b>Последовательная конверсия между этапами:</b>"]
    for step in data["steps"]:
        source_users = step["from"]
        target_users = step["to"]
        rate = target_users / source_users * 100 if source_users else 0
        lines.append(f"• {step['label']}: {target_users}/{source_users} · {rate:.1f}%")

    material_summary = await db.get_material_engagement_summary(days)
    lines += [
        "", "<b>Learning Space:</b>",
        f"Открыли материалы: {material_summary['opened']} · начали упражнения: {material_summary['started']}",
        f"Завершили/отправили ответы: {material_summary['completed']}",
        f"Материал → упражнение: {material_summary['open_to_start']:.1f}% · начало → завершение: {material_summary['start_to_complete']:.1f}%",
    ]

    notification_stats = await db.get_notification_stats(days)
    lines += ["", "<b>Автоматические сообщения и конверсия:</b>"]
    notification_labels = {
        "nurture_day1_sent": "Прогрев Day 1", "nurture_day2_sent": "Прогрев Day 2",
        "nurture_day3_sent": "Прогрев Day 3", "learning_space_feedback_sent": "Дожим после Learning Space",
        "trial_recovery_1_sent": "Recovery №1", "trial_recovery_2_sent": "Recovery №2",
        "followup_no_activity_sent": "Нет активности", "followup_after_exercise_sent": "После упражнения",
        "followup_after_prices_sent": "После просмотра цен",
    }
    for key, label in notification_labels.items():
        metric = notification_stats["conversion"].get(key)
        if metric:
            rate = metric["clicked"] / metric["recipients"] * 100 if metric["recipients"] else 0
            lines.append(f"• {label}: получили {metric['recipients']} · CTA {metric['clicked']} ({rate:.1f}%) · заявки {metric['submitted']}")
    lines.append("\nТаблица событий: люди — уникальные пользователи, события — все срабатывания. Последовательная воронка учитывает только события в правильном порядке. Когорта — пользователи, зарегистрировавшиеся за период; заявки — уникальные люди, отправившие контакт. Конверсии сообщений учитывают последующие действия до следующего автоматического сообщения, но не доказывают причинную связь.")
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

