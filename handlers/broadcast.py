import asyncio
import html
import logging

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import database as db
from handlers.funnel import _ask_trial_contact

router = Router()
log = logging.getLogger(__name__)
_tasks: set = set()


def _is_admin(uid: int) -> bool:
    return uid in config.ADMIN_IDS


def promo_keyboard(bid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Записаться на разбор уровня", callback_data=f"promo:trial:{bid}")],
        [InlineKeyboardButton(text="🔕 Не присылать акции и иные рассылки", callback_data=f"promo:stop:{bid}")],
    ])


def _parse_filters(args: str | None):
    goal = level = None
    for part in (args or "").split():
        if part.startswith("goal="):
            goal = part[5:].lower()
        elif part.startswith("level="):
            level = part[6:].upper()
    return goal, level


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return
    src = message.reply_to_message
    if not src:
        await message.answer(
            "Напиши текст рассылки (можно с картинкой и форматированием), "
            "затем ответь на него командой /broadcast.\n"
            "Фильтры: /broadcast goal=work level=B1"
        )
        return
    goal, level = _parse_filters(command.args)
    ids = await db.broadcast_audience(goal=goal, level=level)
    if not ids:
        await message.answer("Под условия сейчас никто не подходит.")
        return
    await src.copy_to(message.chat.id, reply_markup=promo_keyboard(0))  # превью
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"✅ Отправить {len(ids)} чел.",
            callback_data=f"bc:go:{src.message_id}:{goal or '-'}:{level or '-'}",
        ),
        InlineKeyboardButton(text="✖️ Отмена", callback_data="bc:cancel"),
    ]])
    await src.reply(f"Выше превью. Получат: {len(ids)} чел. Отправляем?", reply_markup=kb)


@router.callback_query(F.data == "bc:cancel")
async def bc_cancel(callback: CallbackQuery):
    if _is_admin(callback.from_user.id):
        await callback.message.edit_text("Отменено.")
    await callback.answer()


@router.callback_query(F.data.startswith("bc:go:"))
async def bc_go(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer()
        return
    _, _, mid, goal, level = callback.data.split(":")
    goal = None if goal == "-" else goal
    level = None if level == "-" else level
    ids = await db.broadcast_audience(goal=goal, level=level)

    src = callback.message.reply_to_message
    preview = (src.text or src.caption or "медиа") if src else "—"
    bid = await db.create_broadcast(preview, len(ids))

    await callback.message.edit_text(f"Рассылка #{bid} пошла: {len(ids)} чел. Отчёт пришлю по окончании.")
    await callback.answer()
    task = asyncio.create_task(_run_broadcast(bot, callback.from_user.id, int(mid), ids, bid))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run_broadcast(bot: Bot, admin_id: int, mid: int, ids: list[int], bid: int) -> None:
    sent = failed = 0
    for uid in ids:
        for _attempt in range(2):
            try:
                await bot.copy_message(uid, from_chat_id=admin_id, message_id=mid,
                                       reply_markup=promo_keyboard(bid))
                await db.log_broadcast_sent(bid, uid)
                sent += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                await db.update_user(uid, blocked=1)
                failed += 1
                break
            except Exception:
                log.exception("Рассылка #%s: ошибка отправки %s", bid, uid)
                failed += 1
                break
        else:
            failed += 1
        await asyncio.sleep(0.07)
    await db.finish_broadcast(bid, sent, failed)
    await bot.send_message(admin_id, f"✅ Рассылка #{bid} завершена: доставлено {sent}, не доставлено {failed}.")


@router.callback_query(F.data.startswith("promo:trial:"))
async def promo_trial(callback: CallbackQuery):
    bid = int(callback.data.split(":")[2])
    await db.mark_broadcast_event(bid, callback.from_user.id, "clicked")
    await _ask_trial_contact(callback.message, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("promo:stop:"))
async def promo_stop(callback: CallbackQuery):
    bid = int(callback.data.split(":")[2])
    await db.update_user(callback.from_user.id, unsubscribed=1)
    await db.mark_broadcast_event(bid, callback.from_user.id, "unsubscribed")
    await callback.message.answer("Готово, акции больше не присылаю. Материалы и разбор уровня — по-прежнему в /menu 🙂")
    await callback.answer()


@router.message(Command("broadcasts"))
async def cmd_broadcasts(message: Message):
    if not _is_admin(message.from_user.id):
        return
    rows = await db.get_broadcast_report()
    if not rows:
        await message.answer("Рассылок пока не было.")
        return
    lines = ["<b>Последние рассылки</b>", "<pre>", "#   Дата        Отпр  Клик  Откл"]
    for r in rows:
        lines.append(f"{r['id']:<3} {r['created_at'][:10]} {r['sent']:>5} {r['clicks']:>5} {r['unsubs']:>5}")
    lines.append("</pre>")
    lines += [f"#{r['id']}: {html.escape(r['preview'])}" for r in rows]
    await message.answer("\n".join(lines), parse_mode="HTML")
