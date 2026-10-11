# -*- coding: utf-8 -*-
"""
Конфигурация бота.

Приоритет: переменные окружения (панель Bothost) → локальный config.py → значения по умолчанию.

На BotHost токен подставляется платформой автоматически в BOT_TOKEN
(также доступны алиасы API_TOKEN и TELEGRAM_BOT_TOKEN).
Никакие секреты не хранятся в коде.
"""

import os

try:
    from shutil import which
except ImportError:  # pragma: no cover
    which = None


def env(name, default=""):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name, default=0):
    try:
        return int(os.environ.get(name, "").strip())
    except (TypeError, ValueError):
        return default


def env_int_list(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return list(default)
    out = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(int(chunk))
        except ValueError:
            log_line(f"ADMIN_IDS: игнорируем нечисловое значение {chunk!r}")
    return out or list(default)


def log_line(message):
    print(message, flush=True)


# --- Telegram ---
BOT_TOKEN = env("BOT_TOKEN") or env("API_TOKEN") or env("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = env_int_list("ADMIN_IDS", [397809686, 126426602])
CHANNEL_ID = env("CHANNEL_ID", "@troizadm")

# --- Сайт (API) ---
SITE_URL = env("SITE_URL", "https://dmtroizahram.ru")
BOT_API_KEY = env("BOT_API_KEY", "")

# --- VK ---
VK_TOKEN = env("VK_TOKEN", "")
VK_OWNER_ID = env_int("VK_OWNER_ID", -211288911)

# --- MAX ---
MAX_TOKEN = env("MAX_TOKEN", "")
MAX_CHAT_ID = env("MAX_CHAT_ID", "")

# --- Заголовок поста с расписанием ---
SCHEDULE_HEADER = env(
    "SCHEDULE_HEADER",
    "⛪ Расписание богослужений\nТроицкий храм, г. Дмитров\n",
)

# --- Подключение к Telegram API ---
API_BASE_URL = env("API_BASE_URL", "")
PROXY_URL = env("PROXY_URL", "")

# --- Хранилище ---
# На BotHost персистентный том — /app/data, иначе SQLite обнуляется при рестарте.
_LOCAL_DB = "bot.db"
_default_data_dir = "/app/data" if os.path.isdir("/app") else ""
DATA_DIR = env("DATA_DIR", _default_data_dir)
DB_PATH = os.path.join(DATA_DIR, "bot.db") if DATA_DIR else _LOCAL_DB

# Диагностика при старте (без утечки секретов)
if __name__ == "__main__":
    log_line(f"token: {'задан' if BOT_TOKEN else 'НЕ ЗАДАН'}")
    log_line(f"admins: {ADMIN_IDS}")
    log_line(f"channel: {CHANNEL_ID}")
    log_line(f"site: {SITE_URL}")
    log_line(f"bot_api_key: {'задан' if BOT_API_KEY else 'НЕ ЗАДАН'}")
    log_line(f"db_path: {DB_PATH}")
    log_line(f"api_base_url: {API_BASE_URL or 'прямое подключение'}")
    log_line(f"proxy: {PROXY_URL or 'нет'}")
    log_line(f"python: {__import__('sys').version.split()[0]}")
