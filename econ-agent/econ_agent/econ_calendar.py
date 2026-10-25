import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from . import config, fred
from .http_utils import log
from .indicators import INDICATORS


@dataclass
class Event:
    name: str
    when_utc: datetime
    basis: str          # مصدر/درجة اليقين في التوقيت
    importance: str = "high"


def et_to_utc(date_str, hhmm):
    d = date.fromisoformat(date_str)
    h, m = map(int, hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=config.ET).astimezone(timezone.utc)


def _load(name):
    try:
        with open(os.path.join(config.DATA_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.warning("cannot read %s: %s", name, e)
        return {}


def nth_business_day(year, month, n):
    d, count = date(year, month, 1), 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)


def ism_estimates(start: date, end: date):
    """ISM التصنيعي: أول يوم عمل، والخدمي: ثالث يوم عمل (تقديري، دون مراعاة العطل)."""
    out, y, m = [], start.year, start.month
    while date(y, m, 1) <= end:
        for n, name in ((1, "ISM PMI التصنيعي"), (3, "ISM PMI الخدمي")):
            d = nth_business_day(y, m, n)
            if start <= d <= end:
                out.append(Event(name, et_to_utc(d.isoformat(), "10:00"),
                                 "موعد تقديري من القاعدة المعتادة — تحقق من ismworld.org", "high"))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def collect(state, now_utc, days):
    start = now_utc.astimezone(config.ET).date() - timedelta(days=1)
    end = (now_utc + timedelta(days=days)).astimezone(config.ET).date() + timedelta(days=1)
    events, errors = [], []
    for ind in INDICATORS:
        if not ind.calendar:
            continue
        try:
            for ds in fred.upcoming_dates(state, ind.metrics[0].series, start, end):
                events.append(Event(ind.name_ar, et_to_utc(ds, ind.release_time_et),
                                    "جدول FRED الرسمي (الساعة افتراضية حسب عادة الجهة)", ind.importance))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{ind.key}: {e}")
    fomc = _load("fomc_dates.json")
    for ds in fomc.get("decision_dates", []):
        events.append(Event("قرار الفائدة FOMC + البيان", et_to_utc(ds, "14:00"),
                            "تقويم الفيدرالي (ملف data/fomc_dates.json)", "high"))
    events += ism_estimates(start, end)
    for e in _load("manual_events.json").get("events", []):
        try:
            d, t = e["when_et"].split(" ")
            events.append(Event(e["name"], et_to_utc(d, t), "إدخال يدوي", e.get("importance", "medium")))
        except (KeyError, ValueError):
            log.warning("bad manual event: %r", e)
    lo, hi = now_utc, now_utc + timedelta(days=days)
    events = [e for e in events if lo <= e.when_utc <= hi]
    events.sort(key=lambda e: e.when_utc)
    return events, errors
