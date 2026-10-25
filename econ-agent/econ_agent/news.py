import hashlib
import re
from datetime import datetime, timedelta, timezone
from time import mktime



from . import config
from . import state as st
from .http_utils import get, log
from .indicators import NEWS_FEEDS, NEWS_KEYWORDS

_KW = re.compile("|".join(re.escape(k) for k in NEWS_KEYWORDS), re.I)


def item_id(link, title):
    return hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:16]


def fetch_feed(url):
    import feedparser  # استيراد متأخر ليسهل الاختبار دون المكتبة
    r = get(url)
    parsed = feedparser.parse(r.content)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"RSS غير صالح: {parsed.bozo_exception}")
    return parsed.entries


def collect(state, now_utc, feeds=NEWS_FEEDS):
    """يعيد قائمة أخبار جديدة (لم تُرسل سابقًا). أول تشغيل يسجّل الموجود دون إرساله."""
    first_run = not state["seen_news"]
    seen = set(state["seen_news"])
    fresh, new_ids = [], []
    cutoff = now_utc - timedelta(hours=config.NEWS_MAX_AGE_HOURS)
    for name, url, official in feeds:
        try:
            entries = fetch_feed(url)
            st.record(state, f"news:{name}", True)
        except Exception as e:  # noqa: BLE001
            st.record(state, f"news:{name}", False, e)
            log.warning("feed %s failed: %s", name, e)
            continue
        for e in entries:
            title = (e.get("title") or "").strip()
            link = e.get("link") or ""
            if not title:
                continue
            iid = item_id(link, title)
            if iid in seen:
                continue
            new_ids.append(iid)
            seen.add(iid)
            if first_run:
                continue
            ts = e.get("published_parsed") or e.get("updated_parsed")
            when = datetime.fromtimestamp(mktime(ts), timezone.utc) if ts else now_utc
            if when < cutoff:
                continue
            if not official and not _KW.search(title):
                continue
            fresh.append({"source": name, "official": official, "title": title,
                          "link": link, "when": when})
    st.mark_seen(state, new_ids)
    fresh.sort(key=lambda x: (not x["official"], -x["when"].timestamp()))
    return fresh[: config.NEWS_MAX_PER_RUN], first_run
