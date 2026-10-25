"""تحليل قائم على قواعد عامة. لا يتنبأ بالأسعار ولا يضمن اتجاهها."""
from dataclasses import dataclass
from typing import Optional

HAWKISH_TXT = (
    "قراءة أقوى مما يدعم سيناريو بقاء الفائدة مرتفعة لفترة أطول. الأثر الأولي المعتاد: "
    "دعم نسبي للدولار وارتفاع في عوائد السندات، وضغط على الذهب، وأثر متباين على الأسهم "
    "(ضغط عبر العوائد مقابل دعم من قوة الاقتصاد)."
)
DOVISH_TXT = (
    "قراءة أضعف مما يعزز احتمالات التيسير النقدي. الأثر الأولي المعتاد: "
    "ضغط نسبي على الدولار وتراجع في العوائد ودعم للذهب، وأثر متباين على الأسهم "
    "(دعم من توقعات الفائدة مقابل قلق من تباطؤ النمو)."
)
INLINE_TXT = "القراءة قريبة من المرجع؛ الأثر الأولي المتوقع محدود ما لم تختلف التفاصيل الداخلية أو المراجعات."
MIXED_TXT = "الإشارات متضاربة بين مكونات الإصدار؛ الأثر الإجمالي غير واضح وقد يتحدد بالمكوّن الذي يركز عليه السوق."
CAVEAT = (
    "⚠️ هذه علاقات شائعة وليست قواعد ثابتة: قد يختلف الأثر بحسب ما كان مسعّرًا قبل الصدور، "
    "والمراجعات، وبقية البيانات، وتصريحات الفيدرالي، والعوامل الجيوسياسية (فالذهب مثلًا قد يرتفع "
    "رغم بيانات قوية إذا هيمن الطلب على الملاذ الآمن)."
)


@dataclass
class Verdict:
    verdict: str            # hawkish | dovish | inline
    ref_value: Optional[float]
    ref_label: str          # "التوقع" أو "السابق"
    diff: float
    surprise_known: bool    # True إذا كان المرجع توقعات السوق فعلًا


def analyze(metric, actual, previous, consensus=None):
    if actual is None:
        return None
    if consensus is not None:
        ref, label, known = consensus, "التوقع", True
    elif previous is not None:
        ref, label, known = previous, "السابق", False
    else:
        return None
    diff = actual - ref
    if abs(diff) <= metric.tol:
        v = "inline"
    else:
        up = diff > 0
        v = "hawkish" if up == metric.hawkish_up else "dovish"
    return Verdict(v, ref, label, diff, known)


def overall(verdicts):
    s = {v.verdict for v in verdicts if v}
    if not s:
        return None
    if s == {"inline"}:
        return INLINE_TXT
    if s == {"hawkish"} or s == {"hawkish", "inline"}:
        return HAWKISH_TXT
    if s == {"dovish"} or s == {"dovish", "inline"}:
        return DOVISH_TXT
    return MIXED_TXT


VERDICT_AR = {"hawkish": "أعلى/أقوى من المرجع (صقري)", "dovish": "أضعف من المرجع (حمائمي)",
              "inline": "مطابق تقريبًا للمرجع"}
