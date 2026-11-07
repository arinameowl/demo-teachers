"""Last-resort responses for messages and callbacks not handled elsewhere."""

from aiogram import Router
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import texts

router = Router()


@router.message()
async def unhandled_message(message: Message):
    if not message.from_user:
        return
    await db.create_user_if_missing(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        source="direct",
    )
    if message.text and message.text.startswith("/"):
        await db.update_user(message.from_user.id, awaiting_contact=0)
        reply = (
            "Не удалось распознать эту команду. Используйте меню ниже — "
            "там собраны основные разделы The Teachers."
        )
    elif message.text:
        reply = texts.UNKNOWN_TEXT
    else:
        reply = texts.UNKNOWN_MEDIA
    await message.answer(reply, reply_markup=kb.main_menu_keyboard())


@router.callback_query()
async def unhandled_callback(callback: CallbackQuery):
    await callback.answer("Эта кнопка больше не активна. Откройте меню и выберите нужный раздел.", show_alert=True)
    if callback.message:
        await callback.message.answer("Главное меню The Teachers:", reply_markup=kb.main_menu_keyboard())
