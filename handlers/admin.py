import os

from aiogram import Router
from aiogram.filters import Command
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
