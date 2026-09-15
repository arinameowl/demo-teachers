import asyncio
import json
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

logging.basicConfig(level=logging.INFO)

# Токен бота: задаётся через переменную окружения BOT_TOKEN на хостинге,
# либо для локального теста можно временно подставить строкой ниже.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_ОТ_BOTFATHER")

MATERIALS_FILE = os.path.join(os.path.dirname(__file__), "materials.json")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def load_materials() -> dict:
    """Читаем файл с материалами заново при каждом запросе,
    чтобы изменения в materials.json подхватывались без перезапуска бота."""
    with open(MATERIALS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ВАЖНО: Telegram ограничивает длину callback_data 64 байтами.
# Названия категорий/сериалов на кириллице легко превышают лимит,
# поэтому в кнопках передаём не сами названия, а их порядковый номер (индекс),
# а настоящее название каждый раз достаём из materials.json по этому номеру.


def _button_title(item: dict, idx: int, fallback: str = "Материал") -> str:
    """Название кнопки: title, если есть; иначе text/about (обрезанные); иначе заглушка с номером."""
    title = item.get("title")
    if title:
        return title
    text = item.get("text") or item.get("about")
    if text:
        return text if len(text) <= 60 else text[:57] + "..."
    return f"{fallback} {idx + 1}"


def languages_keyboard() -> InlineKeyboardMarkup:
    data = load_materials()
    buttons = [
        [InlineKeyboardButton(text=lang, callback_data=f"lang:{i}")]
        for i, lang in enumerate(data.keys())
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def levels_keyboard(lang_i: int) -> InlineKeyboardMarkup:
    data = load_materials()
    langs = list(data.keys())
    lang = langs[lang_i]
    levels = data.get(lang, {})
    buttons = [
        [InlineKeyboardButton(text=level, callback_data=f"level:{lang_i}:{i}")]
        for i, level in enumerate(levels.keys())
    ]
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="back:languages")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def categories_keyboard(lang_i: int, level_i: int) -> InlineKeyboardMarkup:
    lang, level, _ = resolve_level(lang_i, level_i)
    data = load_materials()
    categories = data.get(lang, {}).get(level, {})
    buttons = [
        [InlineKeyboardButton(text=cat, callback_data=f"cat:{lang_i}:{level_i}:{i}")]
        for i, cat in enumerate(categories.keys())
    ]
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"back:levels:{lang_i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def items_keyboard(lang_i: int, level_i: int, cat_i: int) -> InlineKeyboardMarkup:
    lang, level, cat = resolve_category(lang_i, level_i, cat_i)
    data = load_materials()
    items = data.get(lang, {}).get(level, {}).get(cat, [])
    buttons = []
    for idx, item in enumerate(items):
        buttons.append(
            [InlineKeyboardButton(
                text=_button_title(item, idx),
                callback_data=f"item:{lang_i}:{level_i}:{cat_i}:{idx}",
            )]
        )
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"back:categories:{lang_i}:{level_i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def shows_keyboard(lang_i: int, level_i: int, cat_i: int) -> InlineKeyboardMarkup:
    """Клавиатура списка сериалов внутри категории."""
    lang, level, cat = resolve_category(lang_i, level_i, cat_i)
    data = load_materials()
    shows = data.get(lang, {}).get(level, {}).get(cat, {})
    buttons = [
        [InlineKeyboardButton(text=show, callback_data=f"show:{lang_i}:{level_i}:{cat_i}:{i}")]
        for i, show in enumerate(shows.keys())
    ]
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"back:categories:{lang_i}:{level_i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def episodes_keyboard(lang_i: int, level_i: int, cat_i: int, show_i: int) -> InlineKeyboardMarkup:
    """Клавиатура списка эпизодов внутри конкретного сериала."""
    lang, level, cat, show = resolve_show(lang_i, level_i, cat_i, show_i)
    data = load_materials()
    episodes = data.get(lang, {}).get(level, {}).get(cat, {}).get(show, [])
    buttons = []
    for idx, ep in enumerate(episodes):
        buttons.append(
            [InlineKeyboardButton(
                text=_button_title(ep, idx, fallback="Эпизод"),
                callback_data=f"ep:{lang_i}:{level_i}:{cat_i}:{show_i}:{idx}",
            )]
        )
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"back:shows:{lang_i}:{level_i}:{cat_i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Вспомогательные функции: переводим индексы обратно в настоящие названия ---

def resolve_lang(lang_i: int) -> str:
    data = load_materials()
    return list(data.keys())[lang_i]


def resolve_level(lang_i: int, level_i: int):
    data = load_materials()
    lang = list(data.keys())[lang_i]
    level = list(data.get(lang, {}).keys())[level_i]
    return lang, level, data


def resolve_category(lang_i: int, level_i: int, cat_i: int):
    lang, level, data = resolve_level(lang_i, level_i)
    cat = list(data.get(lang, {}).get(level, {}).keys())[cat_i]
    return lang, level, cat


def resolve_show(lang_i: int, level_i: int, cat_i: int, show_i: int):
    lang, level, cat = resolve_category(lang_i, level_i, cat_i)
    data = load_materials()
    shows = data.get(lang, {}).get(level, {}).get(cat, {})
    show = list(shows.keys())[show_i]
    return lang, level, cat, show


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Выбери язык, чтобы получить материал:",
        reply_markup=languages_keyboard(),
    )


@dp.callback_query(F.data == "back:languages")
async def back_to_languages(callback: CallbackQuery):
    await callback.message.edit_text("Выбери язык:", reply_markup=languages_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery):
    lang_i = int(callback.data.split(":")[1])
    lang = resolve_lang(lang_i)
    await callback.message.edit_text(f"{lang}. Выбери уровень:", reply_markup=levels_keyboard(lang_i))
    await callback.answer()


@dp.callback_query(F.data.startswith("back:levels:"))
async def back_to_levels(callback: CallbackQuery):
    lang_i = int(callback.data.split(":")[2])
    lang = resolve_lang(lang_i)
    await callback.message.edit_text(f"{lang}. Выбери уровень:", reply_markup=levels_keyboard(lang_i))
    await callback.answer()


@dp.callback_query(F.data.startswith("level:"))
async def choose_level(callback: CallbackQuery):
    _, lang_i, level_i = callback.data.split(":")
    lang_i, level_i = int(lang_i), int(level_i)
    lang, level, _ = resolve_level(lang_i, level_i)
    await callback.message.edit_text(
        f"{lang} · {level}. Выбери категорию:",
        reply_markup=categories_keyboard(lang_i, level_i),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("back:categories:"))
async def back_to_categories(callback: CallbackQuery):
    _, _, lang_i, level_i = callback.data.split(":")
    lang_i, level_i = int(lang_i), int(level_i)
    lang, level, _ = resolve_level(lang_i, level_i)
    await callback.message.edit_text(
        f"{lang} · {level}. Выбери категорию:",
        reply_markup=categories_keyboard(lang_i, level_i),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery):
    _, lang_i, level_i, cat_i = callback.data.split(":")
    lang_i, level_i, cat_i = int(lang_i), int(level_i), int(cat_i)
    lang, level, cat = resolve_category(lang_i, level_i, cat_i)
    data = load_materials()
    content = data.get(lang, {}).get(level, {}).get(cat, [])
    if not content:
        await callback.answer("Пока нет материалов в этой категории", show_alert=True)
        return

    if isinstance(content, dict):
        # Категория организована по сериалам: cat -> {название сериала: [эпизоды]}
        await callback.message.edit_text(
            f"{lang} · {level} · {cat}. Выбери сериал:",
            reply_markup=shows_keyboard(lang_i, level_i, cat_i),
        )
    else:
        # Обычная плоская категория: cat -> [материалы]
        await callback.message.edit_text(
            f"{lang} · {level} · {cat}. Выбери материал:",
            reply_markup=items_keyboard(lang_i, level_i, cat_i),
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("back:shows:"))
async def back_to_shows(callback: CallbackQuery):
    _, _, lang_i, level_i, cat_i = callback.data.split(":")
    lang_i, level_i, cat_i = int(lang_i), int(level_i), int(cat_i)
    lang, level, cat = resolve_category(lang_i, level_i, cat_i)
    await callback.message.edit_text(
        f"{lang} · {level} · {cat}. Выбери сериал:",
        reply_markup=shows_keyboard(lang_i, level_i, cat_i),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("show:"))
async def choose_show(callback: CallbackQuery):
    _, lang_i, level_i, cat_i, show_i = callback.data.split(":")
    lang_i, level_i, cat_i, show_i = int(lang_i), int(level_i), int(cat_i), int(show_i)
    lang, level, cat, show = resolve_show(lang_i, level_i, cat_i, show_i)
    await callback.message.edit_text(
        f"{show}. Выбери эпизод:",
        reply_markup=episodes_keyboard(lang_i, level_i, cat_i, show_i),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("ep:"))
async def send_episode(callback: CallbackQuery):
    _, lang_i, level_i, cat_i, show_i, idx = callback.data.split(":")
    lang_i, level_i, cat_i, show_i, idx = int(lang_i), int(level_i), int(cat_i), int(show_i), int(idx)
    lang, level, cat, show = resolve_show(lang_i, level_i, cat_i, show_i)
    data = load_materials()
    episodes = data.get(lang, {}).get(level, {}).get(cat, {}).get(show, [])
    if idx >= len(episodes):
        await callback.answer("Эпизод не найден", show_alert=True)
        return
    ep = episodes[idx]

    text = f"<b>{show} — {ep.get('title', '')}</b>"
    about = ep.get("about")
    if about:
        text += f"\n\n{about}"
    file_url = ep.get("file_url")
    if file_url:
        text += f"\n\n🔗 {file_url}"
    tasks_url = ep.get("tasks_url")
    if tasks_url:
        text += f"\n\n📝 Задания: {tasks_url}"
    await callback.message.answer(text, parse_mode="HTML")

    await callback.answer()


@dp.callback_query(F.data.startswith("item:"))
async def send_item(callback: CallbackQuery):
    _, lang_i, level_i, cat_i, idx = callback.data.split(":")
    lang_i, level_i, cat_i, idx = int(lang_i), int(level_i), int(cat_i), int(idx)
    lang, level, cat = resolve_category(lang_i, level_i, cat_i)
    data = load_materials()
    items = data.get(lang, {}).get(level, {}).get(cat, [])
    if idx >= len(items):
        await callback.answer("Материал не найден", show_alert=True)
        return
    item = items[idx]
    text = f"<b>{item.get('title', '')}</b>\n\n{item.get('text', '')}"
    file_url = item.get("file_url")
    if file_url:
        text += f"\n\n🔗 {file_url}"
    tasks_url = item.get("tasks_url")
    if tasks_url:
        text += f"\n\n📝 Задания: {tasks_url}"
    await callback.message.answer(text, parse_mode="HTML")

    await callback.answer()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
