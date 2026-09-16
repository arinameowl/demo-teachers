import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import database as db
import keyboards as kb
import texts

router = Router()
log = logging.getLogger(__name__)


class TrialForm(StatesGroup):
    waiting_contact = State()


# ---------- Главное меню ----------

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Меню:", reply_markup=kb.main_menu_keyboard())


@router.callback_query(F.data == "menu:quiz")
async def cb_menu_quiz(callback: CallbackQuery):
    await callback.message.edit_text(texts.LEVEL_CHOICE_QUESTION, reply_markup=kb.level_choice_keyboard())
    await callback.answer()


# ---------- Пробный урок ----------

async def _ask_trial_contact(target: Message, state: FSMContext):
    await state.set_state(TrialForm.waiting_contact)
    await target.answer(texts.TRIAL_ASK_CONTACT)


@router.message(Command("trial"))
async def cmd_trial(message: Message, state: FSMContext):
    await _ask_trial_contact(message, state)


@router.callback_query(F.data == "menu:trial")
async def cb_menu_trial(callback: CallbackQuery, state: FSMContext):
    await _ask_trial_contact(callback.message, state)
    await callback.answer()


@router.message(TrialForm.waiting_contact)
async def save_trial_contact(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await db.update_user(message.from_user.id, trial_requested=1, contact_info=message.text)
    await message.answer(texts.TRIAL_THANKS)

    if config.MANAGER_CHAT_ID:
        try:
            user = message.from_user
            await bot.send_message(
                int(config.MANAGER_CHAT_ID),
                f"🔥 Новая заявка на пробный урок!\n"
                f"Пользователь: @{user.username or '—'} (id {user.id})\n"
                f"Контакт: {message.text}",
            )
        except Exception:
            log.exception("Не удалось уведомить менеджера о заявке")


# ---------- Лист ожидания курса по сериалам ----------

async def _join_waitlist(target: Message, user_id: int):
    await db.update_user(user_id, waitlist_joined=1)
    await target.answer(texts.COURSE_WAITLIST_CONFIRM)


@router.message(Command("course"))
async def cmd_course(message: Message):
    await _join_waitlist(message, message.from_user.id)


@router.callback_query(F.data == "menu:course")
async def cb_menu_course(callback: CallbackQuery):
    await _join_waitlist(callback.message, callback.from_user.id)
    await callback.answer()


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
