import logging
import re

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
import quiz
import texts

router = Router()
log = logging.getLogger(__name__)

class Quiz(StatesGroup):
    in_progress = State()


def _level_result_text(level: str, goal: str | None) -> str:
    context = texts.GOAL_LEVEL_CONTEXT.get(goal, "")
    parts = [f"Ваш ориентировочный уровень — {level}.", texts.LEVEL_COMMENTS[level]]
    if context:
        parts.append(context)
    parts.append("Подборка готова. Откройте Learning Space, чтобы перейти к материалам и упражнениям.")
    return "\n\n".join(parts)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    start_source = (command.args or "direct").strip()[:80]
    await db.create_user_if_missing(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        source=start_source or "direct",
    )
    await db.log_funnel_event(message.from_user.id, "start", start_source or "direct")
    await db.update_user(message.from_user.id, awaiting_contact=0)
    if command.args == "learning_space_return":
        await db.log_funnel_event(message.from_user.id, "learning_space_returned_to_bot")
        await message.answer(
            "Вы вернулись из Learning Space. Следующий шаг — познакомиться с преподавателем, "
            "обсудить ваши цели и получить персональную карту обучения Your Learning Map.",
            reply_markup=kb.learning_return_keyboard(),
        )
        return
    await message.answer(texts.WELCOME, parse_mode="HTML", reply_markup=kb.start_keyboard())


@router.callback_query(F.data == "start:materials")
async def start_material_selection(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await db.update_user(callback.from_user.id, awaiting_contact=0)
    await callback.message.answer(texts.GOAL_QUESTION, reply_markup=kb.goal_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("goal:"))
async def choose_goal(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    goal = callback.data.split(":")[1]
    await db.update_user(callback.from_user.id, goal=goal)
    await db.log_funnel_event(callback.from_user.id, "goal_selected", goal)
    await callback.message.edit_text(f"Цель обучения: {texts.GOAL_LABELS[goal]}.")
    await callback.message.answer(texts.LEVEL_CHOICE_QUESTION, reply_markup=kb.level_choice_keyboard())
    await callback.answer()


@router.callback_query(F.data == "levelmode:manual")
async def level_manual(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(texts.LEVEL_MANUAL_QUESTION, reply_markup=kb.level_manual_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("levelset:"))
async def level_set(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    level = callback.data.split(":")[1]
    await db.update_user(callback.from_user.id, level=level, level_source="manual", stage="onboarded")
    await db.log_funnel_event(callback.from_user.id, "level_selected", f"manual:{level}")
    user = await db.get_user(callback.from_user.id) or {}
    await callback.message.edit_text(
        _level_result_text(level, user.get("goal")),
        reply_markup=kb.learning_ready_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "levelmode:b2plus")
async def level_b2_plus(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await db.update_user(
        callback.from_user.id,
        level=None,
        level_source="teacher_diagnostic",
        stage="b2plus",
    )
    await db.log_funnel_event(callback.from_user.id, "b2plus_teacher_diagnostic_selected")
    await callback.message.edit_text(
        texts.B2_PLUS_MESSAGE,
        reply_markup=kb.b2_plus_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "levelmode:quiz")
async def level_quiz_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Quiz.in_progress)
    await state.update_data(answers={})
    await callback.message.edit_text(texts.QUIZ_INTRO)
    q = quiz.QUESTIONS[0]
    await callback.message.answer(q["prompt"], reply_markup=kb.quiz_options_keyboard(0, q["options"]))
    await callback.answer()

# Пропуск теста на любом вопросе. Без фильтра по состоянию FSM — так кнопка
# работает и после перезапуска бота, когда состояние квиза уже потеряно.
@router.callback_query(F.data == "quizskip")
async def quiz_skip(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(texts.QUIZ_SKIP_TEXT, reply_markup=kb.level_manual_keyboard())
    await callback.answer()


@router.callback_query(Quiz.in_progress, F.data.startswith("quiz:"))
async def quiz_answer(callback: CallbackQuery, state: FSMContext):
    try:
        _, q_index_str, opt_index_str = callback.data.split(":")
        q_index, opt_index = int(q_index_str), int(opt_index_str)
    except (ValueError, TypeError):
        await callback.answer("Этот вариант ответа больше не активен.", show_alert=True)
        return
    if not 0 <= q_index < len(quiz.QUESTIONS) or not 0 <= opt_index < len(quiz.QUESTIONS[q_index]["options"]):
        await callback.answer("Этот вариант ответа больше не активен.", show_alert=True)
        return

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
    await db.update_user(callback.from_user.id, level=level, level_source="quiz", stage="onboarded")
    await db.log_funnel_event(callback.from_user.id, "level_selected", f"quiz:{level}")
    user = await db.get_user(callback.from_user.id) or {}
    await callback.message.edit_text(
        _level_result_text(level, user.get("goal")),
        reply_markup=kb.learning_ready_keyboard(),
    )
    await callback.answer()
