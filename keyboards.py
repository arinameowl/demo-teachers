from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from texts import GOAL_LABELS


def goal_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"goal:{key}")]
        for key, label in GOAL_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def level_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Пройти мини-тест", callback_data="levelmode:quiz")],
            [InlineKeyboardButton(text="✅ Знаю свой уровень", callback_data="levelmode:manual")],
        ]
    )


def level_manual_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=lvl, callback_data=f"levelset:{lvl}")]
            for lvl in ("A1", "A2", "B1")
        ]
    )


def quiz_options_keyboard(question_index: int, options: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=opt, callback_data=f"quiz:{question_index}:{i}")]
            for i, opt in enumerate(options)
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Материалы", callback_data="menu:materials")],
            [InlineKeyboardButton(text="🎯 Тест на уровень", callback_data="menu:quiz")],
            [InlineKeyboardButton(text="🎬 Курс по сериалам", callback_data="menu:course")],
            [InlineKeyboardButton(text="💬 Бесплатный пробный урок", callback_data="menu:trial")],
            [InlineKeyboardButton(text="💰 Цены и форматы", callback_data="menu:prices")],
            [InlineKeyboardButton(text="👋 Написать нам", callback_data="menu:contact")],
        ]
    )


def trial_cta_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💬 Хочу на пробный урок", callback_data="menu:trial")]]
    )


def course_cta_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎬 В лист ожидания курса", callback_data="menu:course")]]
    )
