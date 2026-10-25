import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone

from . import config
from .http_utils import get, log
from .indicators import ASSETS


@dataclass
class Quote:
    key: str
    name: str
    price: float
    prev: float
    asof: str
    source: str
    decimals: int

    @property
    def pct(self):
        return (self.price / self.prev - 1) * 100 if self.prev else 0.0


def _stooq(symbol):
    r = get("https://stooq.com/q/d/l/", params={"s": symbol, "i": "d"})
    text = r.text.strip()
    if not text.lower().startswith("date"):
        raise RuntimeError(f"Stooq رد غير متوقع: {text[:60]!r}")
    rows = list(csv.DictReader(io.StringIO(text)))
    rows = [x for x in rows if x.get("Close") not in (None, "", "null")]
    if len(rows) < 2:
        raise RuntimeError("Stooq: بيانات غير كافية")
    last, prev = rows[-1], rows[-2]
    return float(last["Close"]), float(prev["Close"]), f"إغلاق {last['Date']}"


def _yahoo(symbol):
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"range": "5d", "interval": "1d"}).json()
    res = j["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    if len(closes) < 2:
        raise RuntimeError("Yahoo: بيانات غير كافية")
    price = res["meta"].get("regularMarketPrice") or closes[-1]
    ts = res["meta"].get("regularMarketTime")
    asof = "—"
    if ts:
        asof = datetime.fromtimestamp(ts, timezone.utc).astimezone(config.TZ).strftime("%Y-%m-%d %H:%M")
    return float(price), float(closes[-2]), asof


PROVIDERS = {"stooq": (_stooq, 2), "yahoo": (_yahoo, 3)}  # (الدالة, فهرس الرمز في ASSETS)


def fetch_quote(asset, providers=None):
    key, name, stooq_sym, yahoo_sym, dec = asset
    errors = []
    for p in providers or config.QUOTE_PROVIDERS:
        fn, _ = PROVIDERS[p]
        sym = stooq_sym if p == "stooq" else yahoo_sym
        try:
            price, prev, asof = fn(sym)
            return Quote(key, name, price, prev, asof, p, dec), None
        except Exception as e:  # noqa: BLE001
            errors.append(f"{p}:{e}")
            log.warning("quote %s via %s failed: %s", key, p, e)
    return None, "; ".join(errors)


def fetch_all(state=None):
    from . import state as st
    quotes, failed = {}, {}
    for a in ASSETS:
        q, err = fetch_quote(a)
        if q:
            quotes[a[0]] = q
        else:
            failed[a[0]] = err
    if state is not None:
        st.record(state, "markets", ok=bool(quotes), msg="; ".join(failed.values())[:150])
    return quotes, failed
