import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import config
import database as db
import keyboards as kb
import texts

router = Router()
log = logging.getLogger(__name__)


# ---------- Главное меню ----------

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Меню:", reply_markup=kb.main_menu_keyboard())


@router.message(Command("quiz"))
async def cmd_quiz(message: Message):
    await message.answer(texts.LEVEL_CHOICE_QUESTION, reply_markup=kb.level_choice_keyboard())


@router.callback_query(F.data == "menu:quiz")
async def cb_menu_quiz(callback: CallbackQuery):
    await callback.message.edit_text(texts.LEVEL_CHOICE_QUESTION, reply_markup=kb.level_choice_keyboard())
    await callback.answer()


# ---------- Пробный урок ----------
#
# Ожидание контакта хранится в БД (поле awaiting_contact), а не в FSM-памяти
# процесса: FSM-хранилище у бота — MemoryStorage, оно живёт только пока жив
# процесс. Если хостинг перезапустит контейнер ровно между вопросом "оставь
# контакт" и ответом человека — FSM-состояние потерялось бы, и сообщение
# с контактом просто пропало бы, не долетев до обработчика. Через БД такой
# рестарт не страшен: флаг переживает перезапуск точно так же, как остальной
# прогресс воронки.

async def _ask_trial_contact(target: Message, user_id: int):
    await db.update_user(user_id, awaiting_contact=1)
    await target.answer(texts.TRIAL_ASK_CONTACT)


@router.message(Command("trial"))
async def cmd_trial(message: Message):
    await _ask_trial_contact(message, message.from_user.id)


@router.callback_query(F.data == "menu:trial")
async def cb_menu_trial(callback: CallbackQuery):
    await _ask_trial_contact(callback.message, callback.from_user.id)
    await callback.answer()


async def _is_awaiting_contact(message: Message) -> bool:
    user = await db.get_user(message.from_user.id)
    return bool(user and user.get("awaiting_contact"))


@router.message(_is_awaiting_contact)
async def save_trial_contact(message: Message, bot: Bot):
    contact_text = message.text or message.contact and message.contact.phone_number or "—"
    await db.update_user(message.from_user.id, trial_requested=1, awaiting_contact=0, contact_info=contact_text)
    await message.answer(texts.TRIAL_THANKS)

    if config.MANAGER_CHAT_ID:
        try:
            user = message.from_user
            await bot.send_message(
                int(config.MANAGER_CHAT_ID),
                f"🔥 Новая заявка на пробный урок!\n"
                f"Пользователь: @{user.username or '—'} (id {user.id})\n"
                f"Контакт: {contact_text}",
            )
        except Exception:
            log.exception("Не удалось уведомить менеджера о заявке")


# ---------- Цены ----------

async def _show_prices(target: Message):
    if config.PRICES_URL:
        await target.answer(f"Все цены и форматы — здесь: {config.PRICES_URL}")
    else:
        await target.answer(texts.PRICES_FALLBACK)


@router.message(Command("prices"))
async def cmd_prices(message: Message):
    await _show_prices(message)


@router.callback_query(F.data == "menu:prices")
async def cb_menu_prices(callback: CallbackQuery):
    await _show_prices(callback.message)
    await callback.answer()


# ---------- Контакт с человеком ----------

async def _show_contact(target: Message):
    await target.answer(texts.CONTACT_TEMPLATE.format(username=config.MANAGER_USERNAME))


@router.message(Command("contact"))
async def cmd_contact(message: Message):
    await _show_contact(message)


@router.callback_query(F.data == "menu:contact")
async def cb_menu_contact(callback: CallbackQuery):
    await _show_contact(callback.message)
    await callback.answer()
