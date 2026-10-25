"""كل الإعدادات تأتي من متغيرات البيئة (GitHub Secrets / Variables)."""
import os
from zoneinfo import ZoneInfo


def env(name, default=""):
    v = os.getenv(name)
    return v.strip() if v and v.strip() else default


TIMEZONE = env("TIMEZONE", "Africa/Casablanca")
TZ = ZoneInfo(TIMEZONE)
ET = ZoneInfo("America/New_York")

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")
FRED_API_KEY = env("FRED_API_KEY")

MORNING_TIME = env("MORNING_TIME", "08:00")
MOVERS_TIME = env("MOVERS_TIME", "22:30")
WEEKLY_CALENDAR_DAY = int(env("WEEKLY_CALENDAR_DAY", "6"))  # 0=الاثنين ... 6=الأحد
WEEKLY_CALENDAR_TIME = env("WEEKLY_CALENDAR_TIME", "20:00")
SEND_WINDOW_MINUTES = int(env("SEND_WINDOW_MINUTES", "180"))

QUOTE_PROVIDERS = [p.strip() for p in env("QUOTE_PROVIDERS", "stooq,yahoo").split(",") if p.strip()]
HEALTH_FAIL_THRESHOLD = int(env("HEALTH_FAIL_THRESHOLD", "3"))
NEWS_MAX_AGE_HOURS = int(env("NEWS_MAX_AGE_HOURS", "12"))
NEWS_MAX_PER_RUN = int(env("NEWS_MAX_PER_RUN", "6"))

STATE_PATH = env("STATE_PATH", "state/state.json")
DATA_DIR = env("DATA_DIR", "data")
DRY_RUN = env("DRY_RUN", "0") == "1"
