from datetime import timedelta

from . import config


def due(now_local, hhmm, key, state, weekdays=None, window_min=None):
    """هل حان موعد التقرير؟ يُرسل مرة واحدة يوميًا خلال نافذة بعد الموعد المضبوط."""
    window_min = window_min or config.SEND_WINDOW_MINUTES
    if weekdays is not None and now_local.weekday() not in weekdays:
        return False
    h, m = map(int, hhmm.split(":"))
    sched = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if not (sched <= now_local < sched + timedelta(minutes=window_min)):
        return False
    return state["sent"].get(key) != now_local.date().isoformat()


def mark_sent(state, key, now_local):
    state["sent"][key] = now_local.date().isoformat()
