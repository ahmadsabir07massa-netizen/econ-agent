import json
import os
import tempfile
from datetime import datetime, timezone

from . import config


def load(path=None):
    path = path or config.STATE_PATH
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        s = {}
    for k, v in (("sent", {}), ("indicators", {}), ("seen_news", []), ("health", {}),
                 ("release_ids", {}), ("meta", {})):
        s.setdefault(k, v)
    return s


def save(state, path=None):
    path = path or config.STATE_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def mark_seen(state, ids, cap=3000):
    state["seen_news"].extend(i for i in ids if i not in state["seen_news"])
    state["seen_news"] = state["seen_news"][-cap:]


def record(state, source, ok, msg=""):
    """سجل صحة المصادر: آخر نجاح وعدد الإخفاقات المتتالية."""
    h = state["health"].setdefault(source, {"fails": 0})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if ok:
        h["fails"] = 0
        h["last_ok"] = now
        h.pop("alerted", None)
    else:
        h["fails"] = h.get("fails", 0) + 1
        h["last_error"] = str(msg)[:200]
        h["last_fail"] = now
