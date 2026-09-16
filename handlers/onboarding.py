import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import quiz
import texts
from handlers.materials import send_portion1

router = Router()
log = logging.getLogger(__name__)


class Quiz(StatesGroup):
    in_progress = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db.create_user_if_missing(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )
    await message.answer(texts.WELCOME)
    await message.answer(texts.GOAL_QUESTION, reply_markup=kb.goal_keyboard())


@router.callback_query(F.data.startswith("goal:"))
async def choose_goal(callback: CallbackQuery, state: FSMContext):
    goal = callback.data.split(":")[1]
    await db.update_user(callback.from_user.id, goal=goal)
    await callback.message.edit_text(f"{texts.GOAL_LABELS[goal]} — понял(а)!")
    await callback.message.answer(texts.LEVEL_CHOICE_QUESTION, reply_markup=kb.level_choice_keyboard())
    await callback.answer()


@router.callback_query(F.data == "levelmode:manual")
async def level_manual(callback: CallbackQuery):
    await callback.message.edit_text(texts.LEVEL_MANUAL_QUESTION, reply_markup=kb.level_manual_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("levelset:"))
async def level_set(callback: CallbackQuery):
    level = callback.data.split(":")[1]
    await db.update_user(callback.from_user.id, level=level, level_source="manual")
    await callback.message.edit_text(f"Записал(а) уровень: {level}.")
    await send_portion1(callback.message, callback.from_user.id, level)
    await callback.answer()


@router.callback_query(F.data == "levelmode:quiz")
async def level_quiz_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Quiz.in_progress)
    await state.update_data(answers={})
    await callback.message.edit_text(texts.QUIZ_INTRO)
    q = quiz.QUESTIONS[0]
    await callback.message.answer(q["prompt"], reply_markup=kb.quiz_options_keyboard(0, q["options"]))
    await callback.answer()


@router.callback_query(Quiz.in_progress, F.data.startswith("quiz:"))
async def quiz_answer(callback: CallbackQuery, state: FSMContext):
    _, q_index_str, opt_index_str = callback.data.split(":")
    q_index, opt_index = int(q_index_str), int(opt_index_str)

    data = await state.get_data()
    answers = data.get("answers", {})
    answers[q_index] = opt_index
    await state.update_data(answers=answers)

    next_index = q_index + 1
    if next_index < len(quiz.QUESTIONS):
        q = quiz.QUESTIONS[next_index]
        await callback.message.edit_text(q["prompt"], reply_markup=kb.quiz_options_keyboard(next_index, q["options"]))
        await callback.answer()
        return

    # Квиз закончен — считаем уровень
    level = quiz.score_to_level({int(k): v for k, v in answers.items()})
    await state.clear()
    await db.update_user(callback.from_user.id, level=level, level_source="quiz")
    await callback.message.edit_text(
        texts.QUIZ_RESULT_TEMPLATE.format(level=level, level_comment=texts.LEVEL_COMMENTS[level])
    )
    await send_portion1(callback.message, callback.from_user.id, level)
    await callback.answer()
