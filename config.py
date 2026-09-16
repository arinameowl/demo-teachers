import os

# Токен лид-бота (ДРУГОЙ бот в BotFather, не путать со студенческим!)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_ЛИД_БОТА")

# Контакт менеджера/преподавателя — на него бот выведет кнопку "Написать нам"
# и в него же продублирует заявки на пробный урок (просто username без @).
MANAGER_USERNAME = os.environ.get("theteachers_manager", "your_manager")

# Числовой user_id менеджера, чтобы бот мог присылать ему заявки автоматически.
# Если не задан — заявки просто сохраняются в базе, менеджер сам их смотрит.
MANAGER_CHAT_ID = os.environ.get("8552229424")

# Ссылка на форму/лендинг с ценами. Если пусто — бот покажет цены текстом из texts.py.
PRICES_URL = os.environ.get("PRICES_URL", “https://theteachers.ru/payment")

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "leadbot.db"))
MATERIALS_PATH = os.environ.get(
    "MATERIALS_PATH", os.path.join(os.path.dirname(__file__), "data", "materials_lead.json")
)

# --- Тайминги воронки (в часах). Меняйте под свой темп прогрева, ---
# --- не трогая остальной код — это единственное место с "магическими числами". ---
PORTION_2_DELAY_HOURS = float(os.environ.get("PORTION_2_DELAY_HOURS", 24))   # книга после подкаста
PORTION_3_DELAY_HOURS = float(os.environ.get("PORTION_3_DELAY_HOURS", 48))   # сериал после книги
FOLLOWUP_DELAY_HOURS = float(os.environ.get("FOLLOWUP_DELAY_HOURS", 96))     # чек-ины после 3-й порции
MAX_FOLLOWUPS = int(os.environ.get("MAX_FOLLOWUPS", 2))                      # сколько чек-инов слать, потом бот замолкает

# Как часто планировщик проверяет базу на "кому пора слать следующую порцию" (минуты)
SCHEDULER_INTERVAL_MINUTES = int(os.environ.get("SCHEDULER_INTERVAL_MINUTES", 30))
