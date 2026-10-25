import time

import requests

from . import config
from .http_utils import log, redact


def chunk(text, limit=3900):
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # سطر طويل جدًا
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


def send(text):
    if config.DRY_RUN:
        print("-----[DRY RUN → Telegram]-----\n" + text + "\n------------------------------")
        return True
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID غير مضبوطين")
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    for part in chunk(text):
        payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": part, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        for attempt in range(4):
            try:
                r = requests.post(url, json=payload, timeout=20)
            except requests.RequestException as e:
                if attempt == 3:
                    raise RuntimeError(redact(e)) from None
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 200:
                break
            if r.status_code == 429:
                wait = r.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(min(int(wait), 30))
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Telegram {r.status_code}: {redact(r.text)[:200]}")
        else:
            raise RuntimeError("فشل إرسال Telegram بعد عدة محاولات")
        time.sleep(0.4)
    log.info("sent telegram message (%d chars)", len(text))
    return True
