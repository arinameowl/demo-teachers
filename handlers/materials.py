import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message

import content
import database as db
import keyboards as kb
import texts

router = Router()
log = logging.getLogger(__name__)


def _render_podcast(item: dict, goal: str | None) -> str:
    intro = texts.PORTION1_INTRO.get(goal, texts.PORTION1_INTRO[None])
    parts = [intro, f"\n\n🎧 <b>{item.get('title', '')}</b>"]
    if item.get("text"):
        parts.append(item["text"])
    if item.get("file_url"):
        parts.append(f"🔗 {item['file_url']}")
    if item.get("tasks"):
        parts.append(f"📝 {item['tasks']}")
    text = "\n\n".join(parts) + texts.PORTION1_TASK + texts.PORTION1_SOFT_CTA
    return text


def _render_book(item: dict, goal: str | None) -> str:
    intro = texts.PORTION2_INTRO.get(goal, texts.PORTION2_INTRO[None])
    parts = [intro, f"\n\n📖 <b>{item.get('title', '')}</b>"]
    if item.get("text"):
        parts.append(item["text"])
    if item.get("file_url"):
        parts.append(f"🔗 {item['file_url']}")
    return "\n\n".join(parts)


def _render_series(series: dict, goal: str | None) -> str:
    show = series["show"]
    ep = series["episode"]
    intro = texts.PORTION3_INTRO.get(goal, texts.PORTION3_INTRO[None])
    parts = [intro, f"\n\n🎬 <b>{show} — {ep.get('title', '')}</b>"]
    if ep.get("file_url"):
        parts.append(f"🔗 {ep['file_url']}")
    if ep.get("tasks_url"):
        parts.append(f"📝 Разбор лексики: {ep['tasks_url']}")
    return "\n\n".join(parts)


async def send_portion1(message: Message, user_id: int, level: str) -> None:
    user = await db.get_user(user_id)
    goal = user.get("goal") if user else None
    item = content.get_podcast(level)
    await message.answer(_render_podcast(item, goal), reply_markup=kb.trial_cta_keyboard())
    await message.answer(texts.MENU_HINT)
    await db.set_portion_sent(user_id, stage="portion1_sent", portions_sent=1)


async def send_portion2(bot: Bot, user_id: int, level: str, goal: str | None) -> None:
    item = content.get_book(level)
    await bot.send_message(user_id, texts.PORTION2_CHECKIN)
    await bot.send_message(user_id, _render_book(item, goal), parse_mode="HTML")
    await db.set_portion_sent(user_id, stage="portion2_sent", portions_sent=2)


async def send_portion3(bot: Bot, user_id: int, level: str, goal: str | None) -> None:
    series = content.get_series(level)
    await bot.send_message(user_id, texts.PORTION3_CHECKIN)
    await bot.send_message(user_id, _render_series(series, goal), parse_mode="HTML")
    await db.set_portion_sent(user_id, stage="portion3_sent", portions_sent=3)


async def send_all_unlocked(message: Message, user_id: int) -> None:
    """/materials — повторно показывает всё, что человеку уже открыто по воронке."""
    user = await db.get_user(user_id)
    if not user or not user.get("level"):
        await message.answer("Сначала пройдём короткий онбординг — нажми /start 🙂")
        return

    level = user["level"]
    goal = user.get("goal")
    portions_sent = user.get("portions_sent", 0)

    await message.answer(_render_podcast(content.get_podcast(level), goal))
    if portions_sent >= 2:
        await message.answer(_render_book(content.get_book(level), goal))
    if portions_sent >= 3:
        await message.answer(_render_series(content.get_series(level), goal))
    if portions_sent < 3:
        await message.answer(
            "Остальное пришлю по расписанию, чтобы не наваливать всё сразу — но если очень "
            "хочется прямо сейчас, просто напиши об этом /contact 🙂"
        )


@router.message(F.text == "/materials")
async def cmd_materials(message: Message):
    await send_all_unlocked(message, message.from_user.id)


@router.callback_query(F.data == "menu:materials")
async def cb_materials(callback: CallbackQuery):
    await send_all_unlocked(callback.message, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "menu:materials")
async def cb_materials(callback: CallbackQuery):
    await send_all_unlocked(callback.message, callback.from_user.id)
    await callback.answer()
