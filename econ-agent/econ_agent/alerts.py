"""كشف صدور بيانات جديدة أو مراجعات، مع منع التكرار عبر state."""
import json
import os
from dataclasses import dataclass, field

from . import config, fred
from . import state as st
from .http_utils import log
from .indicators import INDICATORS

EPS = 1e-9


@dataclass
class Alert:
    ind: object
    kind: str                   # new | revision | change
    date: str
    current: dict
    previous: dict
    revisions: list = field(default_factory=list)   # (label, قديم, جديد)
    consensus: dict = field(default_factory=dict)   # key -> (value, source)


def load_consensus(path=None):
    path = path or os.path.join(config.DATA_DIR, "consensus.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def check_indicator(state, ind, consensus=None):
    """يعيد (Alert|None, القيمة الجديدة للحفظ). لا يعدّل state عند وجود تنبيه؛ المستدعي يحفظ بعد الإرسال."""
    consensus = consensus or {}
    data = {}
    for m in ind.metrics:
        obs = fred.observations(m.series, m.units, limit=3)
        if not obs:
            raise RuntimeError(f"لا توجد بيانات للسلسلة {m.series}")
        data[m.key] = obs
    first = ind.metrics[0].key
    latest_date = data[first][0][0]
    cur = {"date": latest_date, "values": {k: v[0][1] for k, v in data.items()}}
    old = state["indicators"].get(ind.key)

    if old is None:                      # أول تشغيل: تسجيل صامت دون تنبيه
        return None, cur

    def differs(a, b):
        return abs(a - b) > EPS

    if ind.trigger == "value_change":
        changed = [k for k in cur["values"] if k in old["values"] and differs(cur["values"][k], old["values"][k])]
        if not changed:
            return None, cur
        return Alert(ind, "change", latest_date, cur["values"], dict(old["values"])), cur

    if latest_date > old["date"]:
        prev, revs = {}, []
        for m in ind.metrics:
            obs = data[m.key]
            if len(obs) > 1:
                prev[m.key] = obs[1][1]
                if obs[1][0] == old["date"] and m.key in old["values"] and differs(obs[1][1], old["values"][m.key]):
                    revs.append((m.label, old["values"][m.key], obs[1][1]))
        cons = {}
        for m in ind.metrics:
            c = consensus.get(m.key)
            if c and c.get("obs_date") == latest_date and "value" in c:
                cons[m.key] = (float(c["value"]), c.get("source", "غير محدد"))
        return Alert(ind, "new", latest_date, cur["values"], prev, revs, cons), cur

    if latest_date == old["date"] and any(
            k in old["values"] and differs(cur["values"][k], old["values"][k]) for k in cur["values"]):
        return Alert(ind, "revision", latest_date, cur["values"], dict(old["values"])), cur
    return None, cur


def run(state, send_fn, build_fn):
    """يمرّ على كل المؤشرات؛ يرسل التنبيهات ثم يحدّث state فقط عند نجاح الإرسال."""
    consensus = load_consensus()
    sent = 0
    for ind in INDICATORS:
        try:
            alert, new_state = check_indicator(state, ind, consensus)
            st.record(state, "fred", True)
        except Exception as e:  # noqa: BLE001
            st.record(state, "fred", False, e)
            log.warning("indicator %s failed: %s", ind.key, e)
            continue
        if alert is None:
            if ind.key not in state["indicators"]:      # أول تشغيل: تسجيل صامت
                state["indicators"][ind.key] = new_state
            continue
        try:
            send_fn(build_fn(alert))
        except Exception as e:  # noqa: BLE001
            st.record(state, "telegram", False, e)
            log.error("alert send failed (will retry next run): %s", e)
            continue
        st.record(state, "telegram", True)
        state["indicators"][ind.key] = new_state
        sent += 1
    return sent
