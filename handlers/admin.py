import os

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import config
import database as db

router = Router()

STAGE_LABELS = [
    ("new", "Зашли, но не дошли до 1-й порции (застряли в онбординге/квизе)"),
    ("portion1_sent", "Получили порцию 1 — подкаст"),
    ("portion2_sent", "Получили порцию 2 — книга"),
    ("portion3_sent", "Получили порцию 3 — сериал"),
    ("nurtured", "Прошли все чек-ины (воронка отработала полностью)"),
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
             "Дата        Новых  П1   П3  Проб"]
    for r in rows:
        lines.append(f"{r['day']} {r['new_users']:>6} {r['got_p1']:>4} {r['got_p3']:>4} {r['trials']:>5}")
    lines.append(f"Итого      {sum(r['new_users'] for r in rows):>6} "
                 f"{sum(r['got_p1'] for r in rows):>4} {sum(r['got_p3'] for r in rows):>4} "
                 f"{sum(r['trials'] for r in rows):>5}")
    lines.append("</pre>")
    lines.append("Новых = нажали /start в этот день; П1/П3 = дошли до 1-й/3-й порции; Проб = оставили заявку на пробный (из тех, кто пришёл в этот день).")
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("sources"))
async def cmd_sources(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    rows = await db.get_source_stats()
    lines = ["<b>Источники трафика</b>", "<pre>", "Источник              Всего  П1  Проб"]
    for r in rows:
        lines.append(f"{r['src'][:20]:<20} {r['users']:>6} {r['got_p1']:>3} {r['trials']:>5}")
    lines.append("</pre>")
    a = await db.get_activity_summary()
    lines.append(f"Активны за 7 дней: {a['active_7d']}\nЗаблокировали бота: {a['blocked']}")
    await message.answer("\n".join(lines), parse_mode="HTML")
