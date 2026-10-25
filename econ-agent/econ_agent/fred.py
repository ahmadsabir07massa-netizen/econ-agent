from datetime import date

from . import config
from .http_utils import get

BASE = "https://api.stlouisfed.org/fred"


def _get(path, **params):
    if not config.FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY غير مضبوط")
    params.update(api_key=config.FRED_API_KEY, file_type="json")
    return get(f"{BASE}/{path}", params=params).json()


def observations(series_id, units="lin", limit=4):
    """يعيد [(التاريخ, القيمة)] الأحدث أولًا، مع تجاهل القيم الناقصة."""
    j = _get("series/observations", series_id=series_id, units=units,
             sort_order="desc", limit=limit)
    out = []
    for o in j.get("observations", []):
        try:
            out.append((o["date"], float(o["value"])))
        except (KeyError, ValueError):
            continue
    return out


def release_id(state, series_id):
    cache = state.setdefault("release_ids", {})
    if series_id not in cache:
        cache[series_id] = _get("series/release", series_id=series_id)["releases"][0]["id"]
    return cache[series_id]


def upcoming_dates(state, series_id, start: date, end: date):
    rid = release_id(state, series_id)
    j = _get("release/dates", release_id=rid, include_release_dates_with_no_data="true",
             sort_order="asc", realtime_start=start.isoformat(), realtime_end="9999-12-31")
    return [d["date"] for d in j.get("release_dates", [])
            if start.isoformat() <= d["date"] <= end.isoformat()]
