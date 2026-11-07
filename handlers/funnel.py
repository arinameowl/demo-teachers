import logging
import datetime as dt
import html
import re

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, URLInputFile

import config
import database as db
import keyboards as kb
from . import sheets
import texts

router = Router()
log = logging.getLogger(__name__)


# ---------- Главное меню ----------

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await db.update_user(message.from_user.id, awaiting_contact=0)
    await message.answer("The Teachers · Learning Space\n\nВыберите, с чего хотите продолжить:", reply_markup=kb.main_menu_keyboard())


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery):
    await db.update_user(callback.from_user.id, awaiting_contact=0)
    await callback.message.answer("The Teachers · Learning Space\n\nВыберите, с чего хотите продолжить:", reply_markup=kb.main_menu_keyboard())
    await callback.answer()


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
    user = await db.get_user(user_id)
    if user and user.get("trial_requested"):
        await target.answer(
            texts.TRIAL_ALREADY_SUBMITTED,
            reply_markup=kb.trial_submitted_keyboard(),
        )
        return
    await db.update_user(user_id, awaiting_contact=1)
    await db.log_funnel_event(user_id, "trial_cta_clicked")
    await target.answer(texts.TRIAL_ASK_CONTACT, parse_mode="HTML", reply_markup=kb.contact_request_keyboard())


@router.message(Command("trial"))
async def cmd_trial(message: Message):
    await _ask_trial_contact(message, message.from_user.id)


@router.callback_query(F.data == "menu:trial")
async def cb_menu_trial(callback: CallbackQuery):
    await _ask_trial_contact(callback.message, callback.from_user.id)
    await callback.answer()


async def _is_awaiting_contact(message: Message) -> bool:
    # Команды, цены и кнопки меню не должны попадать в сценарий передачи контакта.
    if message.text and message.text.startswith("/"):
        return False
    user = await db.get_user(message.from_user.id)
    return bool(user and user.get("awaiting_contact"))


def _valid_contact_text(value: str) -> bool:
    value = value.strip()
    email_ok = re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value)
    digits = re.sub(r"\D", "", value)
    phone_ok = len(digits) >= 10 and len(digits) <= 15 and bool(re.fullmatch(r"[+\d()\s.-]+", value))
    return bool(email_ok or phone_ok)


@router.message(_is_awaiting_contact)
async def save_trial_contact(message: Message, bot: Bot):
    # Человек передумал
    if message.text == texts.TRIAL_CANCEL_BUTTON:
        await db.update_user(message.from_user.id, awaiting_contact=0)
        await db.log_funnel_event(message.from_user.id, "trial_contact_cancelled")
        await message.answer(
            texts.TRIAL_CANCELLED,
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(texts.OBJECTIONS_INTRO, reply_markup=kb.objections_keyboard())
        return
 
    if message.contact:
        # Не принимаем контакт третьего лица, отправленный из адресной книги.
        if message.contact.user_id and message.contact.user_id != message.from_user.id:
            await message.answer(texts.TRIAL_CONTACT_RETRY, reply_markup=kb.contact_request_keyboard())
            return
        contact_text = message.contact.phone_number
    else:
        contact_text = (message.text or "").strip()

    if not _valid_contact_text(contact_text):
        await message.answer(texts.TRIAL_CONTACT_RETRY, reply_markup=kb.contact_request_keyboard())
        return
 
    await db.update_user(
        message.from_user.id,
        trial_requested=1,
        stage="trial_requested",
        awaiting_contact=0,
        contact_info=contact_text,
        trial_requested_at=dt.datetime.utcnow().isoformat(),
    )
    await db.log_funnel_event(message.from_user.id, "trial_contact_submitted")
    await message.answer(
        texts.TRIAL_THANKS,
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        texts.TRIAL_CANCEL_PROMPT,
        reply_markup=kb.trial_submitted_keyboard(),
    )
 
    user = message.from_user
    row = await db.get_user(user.id) or {}
 
    if config.MANAGER_CHAT_ID:
        try:
            text = (
                "🔥 Новая заявка на пробный урок!\n"
                f"Пользователь: {html.escape(user.full_name)} (@{user.username or '—'}, id {user.id})\n"
                f"Контакт: {html.escape(contact_text)}\n"
                f"Уровень: {row.get('level') or '—'} · цель: {html.escape(texts.GOAL_LABELS.get(row.get('goal'), '—'))} · "
                f"источник: {html.escape(row.get('source') or '—')}\n"
                "Оффер: бесплатный первый урок + Your Learning Map"
            )
            await bot.send_message(int(config.MANAGER_CHAT_ID), text, parse_mode="HTML")
        except Exception:
            log.exception("Не удалось уведомить менеджера о заявке")
 
    # Те же данные — новой строкой в Google-таблицу (если задан SHEETS_WEBHOOK_URL)
    await sheets.append_trial_row(
        name=user.full_name,
        username=user.username,
        user_id=user.id,
        contact=contact_text,
        level=row.get("level"),
        goal=row.get("goal"),
        source=row.get("source"),
    )
 
 


@router.callback_query(F.data == "trial:cancel_submitted")
async def cb_cancel_submitted_trial(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    user_row = await db.get_user(user_id) or {}
    if not user_row.get("trial_requested"):
        await callback.message.answer(
            "Активной заявки на первый урок не найдено. Если хотите записаться, отправьте новую заявку.",
        )
        await callback.answer()
        return

    await db.update_user(
        user_id,
        trial_requested=0,
        awaiting_contact=0,
        contact_info=None,
        trial_requested_at=None,
        stage="trial_cancelled",
    )
    await db.log_funnel_event(user_id, "trial_request_cancelled")
    await callback.message.answer(texts.TRIAL_REQUEST_CANCELLED)
    await callback.message.answer(
        texts.OBJECTIONS_INTRO,
        reply_markup=kb.objections_keyboard(),
    )
    await db.log_funnel_event(user_id, "objections_menu_opened", "after_trial_request_cancelled")

    if config.MANAGER_CHAT_ID:
        try:
            username = f"@{callback.from_user.username}" if callback.from_user.username else "без username"
            await bot.send_message(
                int(config.MANAGER_CHAT_ID),
                "Заявка на первый урок отменена пользователем. "
                f"Пользователь: {callback.from_user.full_name} ({username}, id {user_id}).",
            )
        except Exception:
            log.exception("Не удалось уведомить менеджера об отмене заявки")

    await callback.answer("Заявка отменена")


# ---------- Цены ----------

async def _show_prices(target: Message, user_id: int):
    # Просмотр цен — самостоятельное событие, а не заявка. Снимаем ожидание контакта.
    await db.update_user(user_id, awaiting_contact=0)
    await db.log_funnel_event(user_id, "prices_viewed")
    await target.answer(
        texts.PRICES_FALLBACK,
        parse_mode="HTML",
        reply_markup=kb.prices_keyboard(config.PRICES_URL),
        disable_web_page_preview=True,
    )


@router.message(Command("prices"))
async def cmd_prices(message: Message):
    await _show_prices(message, message.from_user.id)


@router.callback_query(F.data == "menu:prices")
async def cb_menu_prices(callback: CallbackQuery):
    await _show_prices(callback.message, callback.from_user.id)
    await callback.answer()


# ---------- Презентация школы ----------

@router.callback_query(F.data == "menu:school")
async def cb_menu_school(callback: CallbackQuery):
    await db.update_user(callback.from_user.id, awaiting_contact=0)
    await db.log_funnel_event(callback.from_user.id, "school_info_viewed")
    await callback.message.answer(texts.SCHOOL_INTRO, parse_mode="HTML", reply_markup=kb.school_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:method")
async def cb_menu_method(callback: CallbackQuery):
    await db.update_user(callback.from_user.id, awaiting_contact=0)
    await db.log_funnel_event(callback.from_user.id, "method_viewed")
    await callback.message.answer(
        texts.SCHOOL_METHOD,
        parse_mode="HTML",
        reply_markup=kb.school_detail_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:teachers")
async def cb_menu_teachers(callback: CallbackQuery):
    await db.update_user(callback.from_user.id, awaiting_contact=0)
    await db.log_funnel_event(callback.from_user.id, "teachers_viewed")
    await callback.message.answer(
        texts.SCHOOL_TEACHERS_INTRO + "\n\n" + texts.SCHOOL_TEACHERS,
        parse_mode="HTML",
        reply_markup=kb.teachers_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:map_example")
async def cb_menu_map_example(callback: CallbackQuery):
    await db.update_user(callback.from_user.id, awaiting_contact=0)
    await db.log_funnel_event(callback.from_user.id, "map_example_viewed")
    image_url = "https://raw.githubusercontent.com/arinameowl/learning-space/main/assets/learning_map_example.png"
    await callback.message.answer_photo(
        photo=URLInputFile(image_url, filename="learning_map_example.png"),
        caption=texts.SCHOOL_MAP_EXAMPLE_CAPTION,
        parse_mode="HTML",
        reply_markup=kb.school_detail_keyboard(),
    )
    await callback.answer()



# ---------- Возражения и вопросы перед записью ----------

@router.callback_query(F.data == "objections:menu")
async def cb_objections_menu(callback: CallbackQuery):
    await db.log_funnel_event(callback.from_user.id, "objections_menu_opened")
    await callback.message.answer(texts.OBJECTIONS_INTRO, reply_markup=kb.objections_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("objection:"))
async def cb_objection_answer(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    answer = texts.OBJECTION_ANSWERS.get(key)
    if not answer:
        await callback.answer("Не удалось определить вопрос. Выберите вариант еще раз.", show_alert=True)
        return
    await db.log_funnel_event(callback.from_user.id, "objection_selected", key)
    await callback.message.answer(answer, reply_markup=kb.objection_answer_keyboard())
    await callback.answer()


# ---------- Контакт с человеком ----------

async def _show_contact(target: Message, user_id: int):
    await db.update_user(user_id, awaiting_contact=0)
    await db.log_funnel_event(user_id, "manager_contact_requested")
    await target.answer(texts.CONTACT_TEMPLATE.format(username=config.MANAGER_USERNAME))


@router.message(Command("contact"))
async def cmd_contact(message: Message):
    await _show_contact(message, message.from_user.id)


@router.callback_query(F.data == "menu:contact")
async def cb_menu_contact(callback: CallbackQuery):
    await _show_contact(callback.message, callback.from_user.id)
    await callback.answer()
