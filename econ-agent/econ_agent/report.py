"""بناء رسائل Telegram (HTML). كل سطر يغلق وسومه بنفسه كي لا ينكسر عند التقسيم."""
import html
from datetime import datetime

from . import analysis, config
from .indicators import FRED_MARKET

AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
CONFIRMED = "🟢 <b>بيانات رسمية مؤكدة</b>"
NEWS_LBL = "🟡 <b>خبر صحفي</b> (لم يُتحقق منه من مصدر ثانٍ)"
ANALYSIS_LBL = "🔵 <b>تحليل آلي</b> (قواعد عامة، وليس توقعًا مؤكدًا)"
DELAY_NOTE = ("⏱ الأسعار مجانية ومؤجلة (إغلاق يومي أو تأخير قد يتجاوز 15 دقيقة) ولا تصلح للتداول اللحظي. "
              "عوائد FRED تتأخر عادةً يومًا.")


def esc(s):
    return html.escape(str(s), quote=False)


def link(url, text):
    return f'<a href="{html.escape(url, quote=True)}">{esc(text)}</a>'


def local(dt_utc):
    return dt_utc.astimezone(config.TZ)


def stamp(dt_utc):
    d = local(dt_utc)
    return f"{AR_DAYS[d.weekday()]} {d:%Y-%m-%d %H:%M} (توقيت المغرب)"


def num(v, dec=1, suffix=""):
    if v is None:
        return "—"
    if suffix == "K":
        return f"{v:+,.{dec}f} ألف"
    return f"{v:,.{dec}f}{suffix}"


def arrow(p):
    return "🔺" if p > 0 else ("🔻" if p < 0 else "▫️")


def fred_link(series):
    return link(f"https://fred.stlouisfed.org/series/{series}", f"FRED:{series}")


# ---------------------------------------------------------------- تنبيه إصدار
def build_alert(a, now_utc):
    ind = a.ind
    head = {"new": "🚨 <b>صدور بيانات جديدة</b>", "revision": "♻️ <b>مراجعة لبيانات سابقة</b>",
            "change": "🚨 <b>تغيّر في سعر الفائدة</b>"}[a.kind]
    lines = [head, f"<b>{esc(ind.name_ar)}</b>", f"🕒 {stamp(now_utc)}",
             f"📆 الفترة: {esc(a.date)}", CONFIRMED, ""]
    verdicts = []
    for m in ind.metrics:
        cur, prev = a.current.get(m.key), a.previous.get(m.key)
        cons = a.consensus.get(m.key)
        row = f"• {esc(m.label)}: <b>{num(cur, m.decimals, m.suffix)}</b>"
        if a.kind == "revision":
            row += f" (كانت {num(prev, m.decimals, m.suffix)})"
        else:
            row += f" | السابق: {num(prev, m.decimals, m.suffix)}"
            row += (f" | التوقع: {num(cons[0], m.decimals, m.suffix)}" if cons else " | التوقع: غير متوفر")
        lines.append(row)
        if m.analyze and a.kind != "revision":
            v = analysis.analyze(m, cur, prev, cons[0] if cons else None)
            if v:
                verdicts.append(v)
                src = "توقعات السوق" if v.surprise_known else "القراءة السابقة فقط (لا توجد توقعات)"
                lines.append(f"   ↳ {analysis.VERDICT_AR[v.verdict]} — المرجع: {src}")
    for label, old, new in a.revisions:
        lines.append(f"♻️ مراجعة: {esc(label)} كانت {old:g} وأصبحت {new:g}")
    if a.consensus:
        srcs = {c[1] for c in a.consensus.values()}
        lines.append("📌 مصدر التوقعات (إدخال يدوي): " + esc("، ".join(srcs)))
    if verdicts:
        lines += ["", ANALYSIS_LBL, esc(analysis.overall(verdicts))]
        if not any(v.surprise_known for v in verdicts):
            lines.append("ℹ️ المقارنة مع السابق لا تعكس \"مفاجأة\" السوق؛ المهم هو الفرق عن التوقعات.")
        lines.append(esc(analysis.CAVEAT))
    elif a.kind == "change":
        lines += ["", ANALYSIS_LBL, esc("تغيير في نطاق الفائدة: راجع بيان الفيدرالي ونبرة المؤتمر الصحفي، فالأثر يعتمد على الفرق عن المسعّر في السوق.")]
    if ind.note:
        lines.append(f"ℹ️ {esc(ind.note)}")
    series = {m.series for m in ind.metrics}
    lines += ["", "🔗 المصدر: " + " ، ".join(fred_link(s) for s in sorted(series))]
    return "\n".join(lines)


# ---------------------------------------------------------------- أخبار
def build_news(items, now_utc):
    lines = [f"📰 <b>أخبار مالية جديدة</b> — {stamp(now_utc)}", ""]
    for it in items:
        tag = "🟢 رسمي" if it["official"] else "🟡 صحفي"
        lines.append(f"{tag} | {esc(it['source'])} | {local(it['when']):%H:%M}")
        lines.append(link(it["link"], it["title"]) if it["link"] else esc(it["title"]))
        lines.append("")
    lines.append("ℹ️ العناوين بلغتها الأصلية دون ترجمة. الأخبار الصحفية قد تحتاج تحققًا من الجهة المصدرة.")
    return "\n".join(lines)


# ---------------------------------------------------------------- تقويم
def build_calendar(events, title, now_utc, errors=()):
    lines = [f"🗓 <b>{esc(title)}</b>", f"🕒 {stamp(now_utc)}", ""]
    if not events:
        lines.append("لا توجد إصدارات مهمة في النطاق المطلوب ضمن المصادر المتاحة.")
    last_day = None
    for e in events:
        d = local(e.when_utc)
        if d.date() != last_day:
            last_day = d.date()
            lines.append(f"\n<b>{AR_DAYS[d.weekday()]} {d:%Y-%m-%d}</b>")
        dot = "🔴" if e.importance == "high" else "🟠"
        lines.append(f"{dot} {d:%H:%M} — {esc(e.name)}")
        lines.append(f"   <i>{esc(e.basis)}</i>")
    if errors:
        lines.append("\n⚠️ تعذّر جلب بعض المواعيد: " + esc("; ".join(errors)[:300]))
    lines.append("\nℹ️ المواعيد قد تتغير؛ تأكد من مواقع الجهات الرسمية. لا تشمل القائمة كل إصدارات العالم.")
    return "\n".join(lines)


# ---------------------------------------------------------------- الأسعار
def market_lines(quotes, failed):
    lines = []
    for key, q in quotes.items():
        lines.append(f"{arrow(q.pct)} {esc(q.name)}: <b>{q.price:,.{q.decimals}f}</b> ({q.pct:+.2f}%)")
    if failed:
        lines.append("⚠️ تعذّر جلب: " + esc("، ".join(failed)))
    srcs = sorted({q.source for q in quotes.values()})
    if quotes:
        asofs = sorted({q.asof for q in quotes.values()})
        lines.append(f"<i>المصدر: {esc('، '.join(srcs))} — {esc(' | '.join(asofs[:3]))}</i>")
    return lines


def fred_market_lines(fm):
    """fm: {key: [(date, value), ...]} الأحدث أولًا"""
    lines = []
    for key, name, series in FRED_MARKET:
        obs = fm.get(key)
        if not obs:
            lines.append(f"⚠️ {esc(name)}: تعذّر الجلب")
            continue
        d, v = obs[0]
        if len(obs) > 1:
            ch = v - obs[1][1]
            if key.startswith("us"):
                lines.append(f"{arrow(ch)} {esc(name)}: <b>{v:.2f}%</b> ({ch * 100:+.0f} نقطة أساس) — {d}")
            else:
                lines.append(f"{arrow(ch)} {esc(name)}: <b>{v:.2f}</b> ({ch / obs[1][1] * 100:+.2f}%) — {d}")
        else:
            lines.append(f"▫️ {esc(name)}: <b>{v:.2f}</b> — {d}")
    lines.append("<i>المصدر: " + " ، ".join(fred_link(s) for _, _, s in FRED_MARKET) + "</i>")
    return lines


def observations_text(quotes, fm):
    """ملاحظات وصفية عن التزامن فقط، دون ادعاء سببية."""
    out = []
    g, d = quotes.get("gold"), quotes.get("dxy")
    if g and d and abs(g.pct) >= 0.2 and abs(d.pct) >= 0.2:
        if g.pct * d.pct < 0:
            out.append("الذهب والدولار تحركا في اتجاهين متعاكسين، وهو نمط شائع تاريخيًا لكنه غير مضمون ولا يثبت سببًا لهذه الجلسة.")
        else:
            out.append("الذهب والدولار تحركا في الاتجاه نفسه، ما يوحي بعوامل أخرى (مثل الطلب على الملاذ الآمن) تتغلب على العلاقة العكسية المعتادة.")
    y, s = fm.get("us10y"), quotes.get("spx")
    if y and len(y) > 1 and s:
        ch = y[0][1] - y[1][1]
        if ch > 0.03 and s.pct < -0.3:
            out.append("ارتفاع عوائد 10 سنوات تزامن مع تراجع S&P 500؛ تزامن شائع لكنه لا يعني بالضرورة أن العوائد هي السبب.")
        elif ch < -0.03 and s.pct > 0.3:
            out.append("تراجع العوائد تزامن مع صعود S&P 500؛ قد يعكس تحسن شهية المخاطرة أو توقعات فائدة أقل.")
    return out


def build_movers(quotes, failed, fm, now_utc):
    lines = [f"📊 <b>أهم التحركات</b> — {stamp(now_utc)}", "", CONFIRMED + " (أرقام الأسواق)", *market_lines(quotes, failed), "",
             "<b>العوائد والدولار الواسع</b>", *fred_market_lines(fm)]
    obs = observations_text(quotes, fm)
    if quotes:
        top = max(quotes.values(), key=lambda q: abs(q.pct))
        lines += ["", f"أكبر حركة بين الأصول المتابعة: {esc(top.name)} ({top.pct:+.2f}%)"]
    if obs:
        lines += ["", ANALYSIS_LBL] + [esc(o) for o in obs]
    lines += ["", DELAY_NOTE]
    return "\n".join(lines)


# ---------------------------------------------------------------- الصباحي
def build_morning(quotes, failed, fm, latest, events, errors, state, now_utc):
    lines = [f"🌅 <b>التقرير الاقتصادي الصباحي</b>", f"🕒 {stamp(now_utc)}", "",
             CONFIRMED + " — الأسواق (آخر إغلاق/سعر متاح)", *market_lines(quotes, failed), "",
             "<b>العوائد والدولار الواسع</b>", *fred_market_lines(fm), "", "<b>آخر قراءات المؤشرات</b>"]
    for name, rows in latest:
        lines.append(f"• <b>{esc(name)}</b>")
        for label, d, text in rows:
            lines.append(f"   {esc(label)}: {text} <i>({esc(d)})</i>")
    lines += ["", "🗓 <b>الإصدارات خلال 48 ساعة</b>"]
    if events:
        for e in events:
            dot = "🔴" if e.importance == "high" else "🟠"
            dd = local(e.when_utc)
            lines.append(f"{dot} {AR_DAYS[dd.weekday()]} {dd:%H:%M} — {esc(e.name)}")
    else:
        lines.append("لا إصدارات مهمة ضمن المصادر المتاحة.")
    if errors:
        lines.append("⚠️ تعذّر جلب بعض المواعيد: " + esc("; ".join(errors)[:200]))
    obs = observations_text(quotes, fm)
    if obs:
        lines += ["", ANALYSIS_LBL] + [esc(o) for o in obs]
    lines += ["", DELAY_NOTE, "", "🩺 <b>حالة التحديث</b>", *health_lines(state)]
    lines.append("\nℹ️ للمعلومات فقط وليست توصية استثمارية أو دعوة لتنفيذ صفقات.")
    return "\n".join(lines)


def health_lines(state):
    out = []
    for src, h in sorted(state["health"].items()):
        ok = h.get("last_ok")
        when = stamp(datetime.fromisoformat(ok)) if ok else "لم ينجح بعد"
        flag = "✅" if h.get("fails", 0) == 0 else f"⚠️ ({h['fails']} إخفاقات متتالية)"
        out.append(f"{flag} {esc(src)} — آخر نجاح: {esc(when)}")
    return out or ["لا سجل بعد."]


def build_health_alert(items, now_utc):
    lines = [f"⚠️ <b>تنبيه: فشل جلب البيانات</b>", f"🕒 {stamp(now_utc)}", ""]
    for src, h in items:
        last = h.get("last_ok")
        lines.append(f"• {esc(src)}: {h['fails']} محاولات فاشلة متتالية. آخر نجاح: "
                     f"{esc(stamp(datetime.fromisoformat(last)) if last else 'لا يوجد')}")
        lines.append(f"   الخطأ: <code>{esc(h.get('last_error', ''))}</code>")
    lines.append("\nقد يكون السبب انقطاعًا مؤقتًا في المصدر أو حدًا للاستخدام. راجع سجل GitHub Actions.")
    return "\n".join(lines)
