"""Navigation to the Learning Space. Learning content is shown only in the Mini App."""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb

router = Router()

LEARNING_SPACE_PROMPT = (
    "Ваша подборка материалов и упражнений находится в Learning Space. "
    "Откройте приложение, чтобы продолжить занятия и отслеживать прогресс."
)


async def _open_learning_space(target: Message, user_id: int) -> None:
    await db.update_user(user_id, awaiting_contact=0)
    await target.answer(LEARNING_SPACE_PROMPT, reply_markup=kb.learning_app_keyboard())


@router.message(Command("materials"))
async def cmd_materials(message: Message):
    await _open_learning_space(message, message.from_user.id)


@router.callback_query(F.data == "menu:materials")
async def cb_materials(callback: CallbackQuery):
    await _open_learning_space(callback.message, callback.from_user.id)
    await callback.answer()
