from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
import config

from texts import GOAL_LABELS, TRIAL_CANCEL_BUTTON, TRIAL_SHARE_BUTTON


def goal_keyboard() -> InlineKeyboardMarkup:
    options = ("travel", "work", "series", "personal")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=GOAL_LABELS[key], callback_data=f"goal:{key}")]
        for key in options
    ])


def start_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Подобрать материал", callback_data="start:materials")],
        [InlineKeyboardButton(text="Бесплатный первый урок", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Об обучении в The Teachers", callback_data="menu:school")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def learning_return_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подобрать материал", callback_data="start:materials")],
        [InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Об обучении в The Teachers", callback_data="menu:school")],
        [InlineKeyboardButton(text="Цены и форматы", callback_data="menu:prices")],
    ])


def contextual_followup_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")]]
    if config.MINI_APP_URL:
        rows.append([InlineKeyboardButton(text="Открыть Learning Space", web_app=WebAppInfo(url=config.MINI_APP_URL))])
    rows.append([InlineKeyboardButton(text="Цены и форматы", callback_data="menu:prices")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def nurture_learning_keyboard(label: str) -> InlineKeyboardMarkup:
    rows = []
    if config.MINI_APP_URL:
        rows.append([InlineKeyboardButton(text=label, web_app=WebAppInfo(url=config.MINI_APP_URL))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nurture_exercise_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Записаться на первый урок", callback_data="menu:trial")]
    ])


def nurture_day3_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Посмотреть пример карты", callback_data="menu:map_example")],
        [InlineKeyboardButton(text="Есть вопросы перед записью?", callback_data="objections:menu")],
        [InlineKeyboardButton(text="Об обучении в The Teachers", callback_data="menu:school")],
    ])



def trial_recovery_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продолжить запись на первый урок", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Есть вопросы", callback_data="objections:menu")],
    ])


def objections_keyboard() -> InlineKeyboardMarkup:
    options = [
        ("format", "Не знаю, какой формат подойдет"),
        ("level", "Не уверен(а) в своем уровне"),
        ("speaking", "Боюсь говорить и ошибаться"),
        ("time", "Не понимаю, сколько времени потребуется"),
        ("teacher", "Хочу сначала познакомиться с преподавателем"),
        ("value", "Не понимаю ценность индивидуальных занятий"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"objection:{key}")]
        for key, label in options
    ] + [
        [InlineKeyboardButton(text="Связаться с менеджером", callback_data="menu:contact")],
        [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
    ])


def objection_answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Записаться на бесплатный первый урок", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Другой вопрос", callback_data="objections:menu")],
        [InlineKeyboardButton(text="Связаться с менеджером", callback_data="menu:contact")],
        [InlineKeyboardButton(text="В главное меню", callback_data="menu:home")],
    ])


def learning_ready_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if config.MINI_APP_URL:
        rows.append([InlineKeyboardButton(text="Открыть Learning Space", web_app=WebAppInfo(url=config.MINI_APP_URL))])
    rows.extend([
        [InlineKeyboardButton(text="Подобрать материал", callback_data="start:materials")],
        [InlineKeyboardButton(text="Об обучении в The Teachers", callback_data="menu:school")],
        [InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def level_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пройти мини-тест", callback_data="levelmode:quiz")],
        [InlineKeyboardButton(text="Знаю свой уровень", callback_data="levelmode:manual")],
        [InlineKeyboardButton(text="B2 и выше — к преподавателю", callback_data="levelmode:b2plus")],
    ])


def b2_plus_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Записаться на бесплатный урок", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Задать вопрос менеджеру", callback_data="menu:contact")],
        [InlineKeyboardButton(text="Вернуться к выбору уровня", callback_data="menu:quiz")],
    ])


def level_manual_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=lvl, callback_data=f"levelset:{lvl}")]
        for lvl in ("A1", "A2", "B1")
    ])


def quiz_options_keyboard(question_index: int, options: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=opt, callback_data=f"quiz:{question_index}:{i}")]
        for i, opt in enumerate(options)
    ]
    rows.append([InlineKeyboardButton(text="Пропустить тестирование", callback_data="quizskip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if config.MINI_APP_URL:
        rows.append([InlineKeyboardButton(text="Открыть Learning Space", web_app=WebAppInfo(url=config.MINI_APP_URL))])
    rows.extend([
        [InlineKeyboardButton(text="Подобрать материал", callback_data="start:materials")],
        [InlineKeyboardButton(text="Об обучении", callback_data="menu:school")],
        [InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Цены и форматы", callback_data="menu:prices")],
        [InlineKeyboardButton(text="Связаться с командой", callback_data="menu:contact")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def learning_app_keyboard() -> InlineKeyboardMarkup | None:
    if not config.MINI_APP_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть Learning Space", web_app=WebAppInfo(url=config.MINI_APP_URL))]
    ])


def trial_cta_keyboard() -> InlineKeyboardMarkup:
    # После серии сначала предлагаем познакомиться со школой, а не сразу просим контакт.
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Узнать о занятиях в The Teachers", callback_data="menu:school")]
    ])


def school_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Как проходят занятия", callback_data="menu:method")],
        [InlineKeyboardButton(text="Познакомиться с преподавателями", callback_data="menu:teachers")],
        [InlineKeyboardButton(text="Посмотреть пример Your Learning Map", callback_data="menu:map_example")],
        *([[InlineKeyboardButton(text="Открыть Learning Space", web_app=WebAppInfo(url=config.MINI_APP_URL))]] if config.MINI_APP_URL else []),
        [InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Цены и форматы", callback_data="menu:prices")],
    ])


def school_detail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Преподаватели", callback_data="menu:teachers")],
        [InlineKeyboardButton(text="Пример Your Learning Map", callback_data="menu:map_example")],
        *([[InlineKeyboardButton(text="Открыть Learning Space", web_app=WebAppInfo(url=config.MINI_APP_URL))]] if config.MINI_APP_URL else []),
        [InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Вернуться к школе", callback_data="menu:school")],
    ])


def teachers_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пример Your Learning Map", callback_data="menu:map_example")],
        *([[InlineKeyboardButton(text="Открыть Learning Space", web_app=WebAppInfo(url=config.MINI_APP_URL))]] if config.MINI_APP_URL else []),
        [InlineKeyboardButton(text="Все преподаватели на сайте", url="https://theteachers.ru")],
        [InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")],
        [InlineKeyboardButton(text="Вернуться к школе", callback_data="menu:school")],
    ])


def prices_keyboard(prices_url: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    if prices_url:
        rows.append([InlineKeyboardButton(text="Посмотреть все форматы на сайте", url=prices_url)])
    rows.extend([
        [InlineKeyboardButton(text="С другом вокруг света", url="https://theteachers.ru/for-our-students")],
        [InlineKeyboardButton(text="Предложение для держателей «Халвы»", url="https://theteachers.ru/special")],
        [InlineKeyboardButton(text="Первый урок + Your Learning Map", callback_data="menu:trial")],
        [InlineKeyboardButton(text="На главную", callback_data="menu:home")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trial_submitted_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отменить заявку", callback_data="trial:cancel_submitted")],
    ])


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TRIAL_SHARE_BUTTON, request_contact=True)],
            [KeyboardButton(text=TRIAL_CANCEL_BUTTON)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
