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

    lines = [
        f"👥 <b>Всего зашло в бота:</b> {stats['total']} (сегодня: {stats['today']})",
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
