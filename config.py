import os

# Токен лид-бота (ДРУГОЙ бот в BotFather, не путать со студенческим!)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_ЛИД_БОТА")

# Контакт менеджера/преподавателя — на него бот выведет кнопку "Написать нам"
# и в него же продублирует заявки на пробный урок (просто username без @).
MANAGER_USERNAME = os.environ.get("MANAGER_USERNAME", "theteachers_manager")
 
# Числовой user_id менеджера, чтобы бот мог присылать ему заявки автоматически.
# Если не задан — заявки просто сохраняются в базе, менеджер сам их смотрит.
MANAGER_CHAT_ID = os.environ.get("MANAGER_CHAT_ID")

# user_id, которым разрешена команда /stats (через запятую, без пробелов).
# Узнать свой id можно через @userinfobot. Без этой переменной /stats никому не ответит.
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "8552229424 , 712799610").split(",") if x.strip().isdigit()]

# Ссылка на форму/лендинг с ценами. Если пусто — бот покажет цены текстом из texts.py.
PRICES_URL = os.environ.get("PRICES_URL", "https://theteachers.ru/payment")

DEFAULT_DB_PATH = "/data/leadbot.db" if os.path.isdir("/data") else os.path.join(os.path.dirname(__file__), "data", "leadbot.db")
DB_PATH = os.environ.get("DB_PATH", DEFAULT_DB_PATH)
MATERIALS_PATH = os.environ.get(
    "MATERIALS_PATH", os.path.join(os.path.dirname(__file__), "data", "materials_lead.json")
)

# --- Контекстные follow-up сообщения воронки (часы после события) ---
FOLLOWUP_NO_ACTIVITY_HOURS = float(os.environ.get("FOLLOWUP_NO_ACTIVITY_HOURS", 24))
FOLLOWUP_AFTER_EXERCISE_HOURS = float(os.environ.get("FOLLOWUP_AFTER_EXERCISE_HOURS", 24))
FOLLOWUP_AFTER_PRICES_HOURS = float(os.environ.get("FOLLOWUP_AFTER_PRICES_HOURS", 24))

# Как часто планировщик проверяет базу на "кому пора слать следующую порцию" (минуты)
SCHEDULER_INTERVAL_MINUTES = int(os.environ.get("SCHEDULER_INTERVAL_MINUTES", 30))

# Публичный HTTPS URL Mini App (домен Amvera). Пустое значение скрывает кнопку.
MINI_APP_URL = os.environ.get("MINI_APP_URL", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "learning_spacebot").lstrip("@")
WEBAPP_HOST = os.environ.get("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.environ.get("PORT", os.environ.get("WEBAPP_PORT", "80")))
