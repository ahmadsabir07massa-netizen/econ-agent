"""نقطة الدخول:  python -m econ_agent <أمر>
run (الافتراضي) | morning | movers | calendar | news | alerts | selfcheck | test-telegram"""
import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from . import alerts, config, econ_calendar as calendar, fred, markets, news, report, telegram
from . import state as st
from .http_utils import log
from .indicators import FRED_MARKET, INDICATORS
from .scheduler import due, mark_sent


def now_utc():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- جامعو البيانات
def fred_market(state):
    out = {}
    for key, _name, series in FRED_MARKET:
        try:
            out[key] = fred.observations(series, "lin", limit=3)
            st.record(state, "fred", True)
        except Exception as e:  # noqa: BLE001
            st.record(state, "fred", False, e)
            log.warning("fred market %s: %s", series, e)
            out[key] = None
    return out


def latest_readings(state):
    rows_all = []
    for ind in INDICATORS:
        rows = []
        for m in ind.metrics:
            try:
                obs = fred.observations(m.series, m.units, limit=2)
                st.record(state, "fred", True)
                if obs:
                    d, v = obs[0]
                    prev = f" | السابق {report.num(obs[1][1], m.decimals, m.suffix)}" if len(obs) > 1 else ""
                    rows.append((m.label, d, f"<b>{report.num(v, m.decimals, m.suffix)}</b>{prev}"))
            except Exception as e:  # noqa: BLE001
                st.record(state, "fred", False, e)
                rows.append((m.label, "—", "⚠️ تعذّر الجلب"))
        rows_all.append((ind.name_ar, rows))
    return rows_all


# ---------------------------------------------------------------- الأوامر
def cmd_alerts(state):
    return alerts.run(state, telegram.send, lambda a: report.build_alert(a, now_utc()))


def cmd_news(state):
    items, first = news.collect(state, now_utc())
    if first:
        log.info("أول تشغيل للأخبار: تم تسجيل العناوين الحالية دون إرسال")
        return 0
    if items:
        telegram.send(report.build_news(items, now_utc()))
    return len(items)


def cmd_calendar(state, days=7, title="تقويم الإصدارات القادمة (7 أيام)"):
    events, errors = calendar.collect(state, now_utc(), days)
    telegram.send(report.build_calendar(events, title, now_utc(), errors))


def cmd_movers(state):
    quotes, failed = markets.fetch_all(state)
    fm = fred_market(state)
    telegram.send(report.build_movers(quotes, failed, fm, now_utc()))


def cmd_morning(state):
    quotes, failed = markets.fetch_all(state)
    fm = fred_market(state)
    latest = latest_readings(state)
    events, errors = calendar.collect(state, now_utc(), 2)
    telegram.send(report.build_morning(quotes, failed, fm, latest, events, errors, state, now_utc()))


def health_alerts(state):
    today = now_utc().astimezone(config.TZ).date().isoformat()
    bad = [(s, h) for s, h in state["health"].items()
           if h.get("fails", 0) >= config.HEALTH_FAIL_THRESHOLD and h.get("alerted") != today]
    if not bad:
        return
    try:
        telegram.send(report.build_health_alert(bad, now_utc()))
        for _s, h in bad:
            h["alerted"] = today
    except Exception as e:  # noqa: BLE001
        log.error("health alert failed: %s", e)


def tick(state):
    """تشغيل دوري (كل 15 دقيقة): تنبيهات الإصدارات + الأخبار + التقارير المجدولة + فحص الصحة."""
    local = now_utc().astimezone(config.TZ)
    steps = [("alerts", lambda: cmd_alerts(state)), ("news", lambda: cmd_news(state))]
    scheduled = [
        ("morning", config.MORNING_TIME, range(0, 5), lambda: cmd_morning(state)),
        ("movers", config.MOVERS_TIME, range(0, 5), lambda: cmd_movers(state)),
        ("weekly_calendar", config.WEEKLY_CALENDAR_TIME, [config.WEEKLY_CALENDAR_DAY], lambda: cmd_calendar(state)),
    ]
    for name, fn in steps:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.error("step %s failed: %s", name, e)
    for key, hhmm, days, fn in scheduled:
        if due(local, hhmm, key, state, weekdays=list(days)):
            try:
                fn()
                mark_sent(state, key, local)
            except Exception as e:  # noqa: BLE001
                log.error("scheduled %s failed (will retry within window): %s", key, e)
    health_alerts(state)


def selfcheck(state):
    print(f"المنطقة الزمنية: {config.TIMEZONE} | الآن: {now_utc().astimezone(config.TZ):%Y-%m-%d %H:%M}")
    print(f"FRED_API_KEY: {'مضبوط' if config.FRED_API_KEY else 'غير مضبوط'} | "
          f"TELEGRAM: {'مضبوط' if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID else 'غير مضبوط'}")
    try:
        print("FRED CPI:", fred.observations("CPIAUCSL", "pch", 2)[:1])
    except Exception as e:  # noqa: BLE001
        print("FRED ✗", e)
    from .indicators import ASSETS, NEWS_FEEDS
    for a in ASSETS:
        for p in config.QUOTE_PROVIDERS:
            q, err = markets.fetch_quote(a, [p])
            print(f"{a[0]:8s} {p:6s}", f"✓ {q.price} ({q.pct:+.2f}%) {q.asof}" if q else f"✗ {err}")
    for name, url, _ in NEWS_FEEDS:
        try:
            print(f"RSS {name}: ✓ {len(news.fetch_feed(url))} عنصر")
        except Exception as e:  # noqa: BLE001
            print(f"RSS {name}: ✗ {e}")


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="econ_agent")
    ap.add_argument("command", nargs="?", default="run",
                    choices=["run", "morning", "movers", "calendar", "news", "alerts", "selfcheck", "test-telegram"])
    args = ap.parse_args(argv)
    state = st.load()
    try:
        if args.command == "run":
            tick(state)
        elif args.command == "morning":
            cmd_morning(state)
        elif args.command == "movers":
            cmd_movers(state)
        elif args.command == "calendar":
            cmd_calendar(state)
        elif args.command == "news":
            cmd_news(state)
        elif args.command == "alerts":
            cmd_alerts(state)
        elif args.command == "selfcheck":
            selfcheck(state)
        elif args.command == "test-telegram":
            telegram.send("✅ اختبار: البوت متصل ويستطيع إرسال الرسائل إليك.")
    except Exception as e:  # noqa: BLE001
        log.error("command %s failed: %s", args.command, e)
        return 1
    finally:
        st.save(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
