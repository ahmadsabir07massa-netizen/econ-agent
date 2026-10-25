import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["DRY_RUN"] = "1"
os.environ["FRED_API_KEY"] = "testkey"

from econ_agent import alerts, analysis, config, econ_calendar, fred, main, markets, news, report, telegram  # noqa: E402
from econ_agent import state as st  # noqa: E402
from econ_agent.indicators import INDICATORS, Metric  # noqa: E402
from econ_agent.scheduler import due, mark_sent  # noqa: E402

CPI = next(i for i in INDICATORS if i.key == "cpi")
NOW = datetime(2026, 10, 26, 7, 5, tzinfo=timezone.utc)  # 08:05 بتوقيت المغرب (UTC+1)


def fake_obs(table):
    def f(series, units="lin", limit=3):
        return table[(series, units)]
    return f


def cpi_table(date_new, mom, prev_mom, prev_date="2026-08-01"):
    t = {}
    for s in ("CPIAUCSL", "CPILFESL"):
        t[(s, "pch")] = [(date_new, mom), (prev_date, prev_mom)]
        t[(s, "pc1")] = [(date_new, 3.0), (prev_date, 3.1)]
    return t


class AnalysisTests(unittest.TestCase):
    def test_hawkish_dovish_inline(self):
        m = Metric("x", "x", "S", tol=0.05, hawkish_up=True)
        self.assertEqual(analysis.analyze(m, 0.4, 0.2).verdict, "hawkish")
        self.assertEqual(analysis.analyze(m, 0.1, 0.2).verdict, "dovish")
        self.assertEqual(analysis.analyze(m, 0.22, 0.2).verdict, "inline")

    def test_unemployment_inverse(self):
        m = Metric("u", "u", "S", tol=0.05, hawkish_up=False)
        self.assertEqual(analysis.analyze(m, 4.5, 4.2).verdict, "dovish")

    def test_consensus_preferred(self):
        m = Metric("x", "x", "S", tol=0.05)
        v = analysis.analyze(m, 0.3, 0.1, consensus=0.3)
        self.assertEqual((v.verdict, v.ref_label, v.surprise_known), ("inline", "التوقع", True))

    def test_no_reference(self):
        self.assertIsNone(analysis.analyze(Metric("x", "x", "S"), 1.0, None))

    def test_mixed(self):
        a = analysis.Verdict("hawkish", 0, "السابق", 1, False)
        b = analysis.Verdict("dovish", 0, "السابق", -1, False)
        self.assertEqual(analysis.overall([a, b]), analysis.MIXED_TXT)


class AlertTests(unittest.TestCase):
    def test_seed_then_new_then_no_repeat(self):
        state = st.load("/nonexistent.json")
        with mock.patch.object(fred, "observations", fake_obs(cpi_table("2026-08-01", 0.2, 0.3, "2026-07-01"))):
            a, new = alerts.check_indicator(state, CPI)
        self.assertIsNone(a)  # أول تشغيل صامت
        state["indicators"]["cpi"] = new
        with mock.patch.object(fred, "observations", fake_obs(cpi_table("2026-09-01", 0.4, 0.2))):
            a, new = alerts.check_indicator(state, CPI)
        self.assertEqual(a.kind, "new")
        self.assertAlmostEqual(a.previous["cpi_mom"], 0.2)
        state["indicators"]["cpi"] = new
        with mock.patch.object(fred, "observations", fake_obs(cpi_table("2026-09-01", 0.4, 0.2))):
            a, _ = alerts.check_indicator(state, CPI)
        self.assertIsNone(a)  # لا تكرار

    def test_revision_of_previous_detected(self):
        state = st.load("/nonexistent.json")
        state["indicators"]["cpi"] = {"date": "2026-08-01", "values": {"cpi_mom": 0.2, "cpi_yoy": 3.1, "core_mom": 0.2, "core_yoy": 3.1}}
        t = cpi_table("2026-09-01", 0.4, 0.3, "2026-08-01")  # السابق عُدّل 0.2 → 0.3
        with mock.patch.object(fred, "observations", fake_obs(t)):
            a, _ = alerts.check_indicator(state, CPI)
        self.assertTrue(any(r[0] == "CPI شهريًا" for r in a.revisions))

    def test_consensus_only_if_dates_match(self):
        state = st.load("/nonexistent.json")
        state["indicators"]["cpi"] = {"date": "2026-08-01", "values": {"cpi_mom": 0.2, "cpi_yoy": 3.1, "core_mom": 0.2, "core_yoy": 3.1}}
        cons = {"cpi_mom": {"obs_date": "2026-09-01", "value": 0.3, "source": "S"},
                "core_mom": {"obs_date": "2026-07-01", "value": 0.9, "source": "old"}}
        with mock.patch.object(fred, "observations", fake_obs(cpi_table("2026-09-01", 0.4, 0.2))):
            a, _ = alerts.check_indicator(state, CPI, cons)
        self.assertIn("cpi_mom", a.consensus)
        self.assertNotIn("core_mom", a.consensus)

    def test_failed_send_keeps_state_for_retry(self):
        state = st.load("/nonexistent.json")
        old = {"date": "2026-08-01", "values": {"cpi_mom": 0.2, "cpi_yoy": 3.1, "core_mom": 0.2, "core_yoy": 3.1}}
        state["indicators"]["cpi"] = dict(old)
        table = cpi_table("2026-09-01", 0.4, 0.2)
        # بقية المؤشرات: نعيد استثناء كي تُتجاهل
        def obs(series, units="lin", limit=3):
            if (series, units) in table:
                return table[(series, units)]
            raise RuntimeError("skip")
        def boom(_):
            raise RuntimeError("telegram down")
        with mock.patch.object(fred, "observations", obs):
            n = alerts.run(state, boom, lambda a: "x")
        self.assertEqual(n, 0)
        self.assertEqual(state["indicators"]["cpi"], old)  # لم يُحدَّث → سيعاد الإرسال لاحقًا
        sent = []
        with mock.patch.object(fred, "observations", obs):
            n = alerts.run(state, sent.append, lambda a: "msg")
        self.assertEqual((n, sent), (1, ["msg"]))

    def test_fed_rate_value_change(self):
        ind = next(i for i in INDICATORS if i.key == "fed_rate")
        state = st.load("/nonexistent.json")
        state["indicators"]["fed_rate"] = {"date": "2026-10-01", "values": {"fed_upper": 4.0, "fed_lower": 3.75}}
        t = {("DFEDTARU", "lin"): [("2026-10-29", 3.75)], ("DFEDTARL", "lin"): [("2026-10-29", 3.5)]}
        with mock.patch.object(fred, "observations", fake_obs(t)):
            a, _ = alerts.check_indicator(state, ind)
        self.assertEqual(a.kind, "change")
        self.assertEqual(a.previous["fed_upper"], 4.0)


class ReportTests(unittest.TestCase):
    def test_alert_message(self):
        state = st.load("/nonexistent.json")
        state["indicators"]["cpi"] = {"date": "2026-08-01", "values": {"cpi_mom": 0.2, "cpi_yoy": 3.1, "core_mom": 0.2, "core_yoy": 3.1}}
        with mock.patch.object(fred, "observations", fake_obs(cpi_table("2026-09-01", 0.4, 0.2))):
            a, _ = alerts.check_indicator(state, CPI)
        msg = report.build_alert(a, NOW)
        self.assertIn("توقيت المغرب", msg)
        self.assertIn("التوقع: غير متوفر", msg)
        self.assertIn("fred.stlouisfed.org", msg)
        self.assertIn("لا توجد توقعات", msg)

    def test_escape_and_chunk_keeps_tags_balanced(self):
        items = [{"source": "S", "official": False, "title": "A <b> & B", "link": "https://x.com/?a=1&b=2", "when": NOW}] * 80
        msg = report.build_news(items, NOW)
        self.assertIn("A &lt;b&gt; &amp; B", msg)
        parts = telegram.chunk(msg, 1000)
        self.assertGreater(len(parts), 1)
        for p in parts:
            self.assertEqual(p.count("<a "), p.count("</a>"))

    def test_morning_and_movers_with_failures(self):
        q = markets.Quote("gold", "الذهب", 4000.0, 3950.0, "إغلاق 2026-10-23", "stooq", 2)
        d = markets.Quote("dxy", "DXY", 99.0, 99.5, "إغلاق", "stooq", 2)
        fm = {"us02y": [("2026-10-23", 3.9), ("2026-10-22", 3.95)], "us10y": None, "usd_broad": None}
        state = st.load("/nonexistent.json")
        st.record(state, "fred", True)
        msg = report.build_movers({"gold": q, "dxy": d}, {"spx": "x"}, fm, NOW)
        self.assertIn("تعذّر", msg)
        self.assertIn("متعاكسين", msg)
        m2 = report.build_morning({"gold": q}, {}, fm, [("CPI", [("a", "d", "<b>1</b>")])], [], ["e"], state, NOW)
        self.assertIn("حالة التحديث", m2)


class InfraTests(unittest.TestCase):
    def test_chunk_basic(self):
        self.assertEqual(telegram.chunk("a\nb", 100), ["a\nb"])
        self.assertTrue(all(len(p) <= 50 for p in telegram.chunk("\n".join(["x" * 20] * 10), 50)))

    def test_due_logic(self):
        state = st.load("/nonexistent.json")
        local = NOW.astimezone(config.TZ)  # 2026-10-26 الاثنين 08:05
        self.assertTrue(due(local, "08:00", "m", state, weekdays=range(5)))
        self.assertFalse(due(local, "09:00", "m", state))      # لم يحن
        self.assertFalse(due(local, "03:00", "m", state))      # خارج النافذة
        mark_sent(state, "m", local)
        self.assertFalse(due(local, "08:00", "m", state))      # أُرسل اليوم
        sunday = datetime(2026, 10, 25, 20, 10, tzinfo=config.TZ)
        self.assertFalse(due(sunday, "08:00", "x", state, weekdays=range(5)))

    def test_timezone_conversion(self):
        # 8:30 صباحًا نيويورك (EDT) يوم 2026-10-28 = 12:30 UTC = 13:30 المغرب
        e = econ_calendar.et_to_utc("2026-10-28", "08:30")
        self.assertEqual(e.hour, 12)
        self.assertEqual(e.astimezone(config.TZ).hour, 13)

    def test_ism_estimates(self):
        ev = econ_calendar.ism_estimates(date(2026, 11, 1), date(2026, 11, 30))
        days = sorted(e.when_utc.astimezone(config.ET).date() for e in ev)
        self.assertEqual(days, [date(2026, 11, 2), date(2026, 11, 4)])

    def test_news_dedupe_and_filter(self):
        state = st.load("/nonexistent.json")
        entries = [
            SimpleNamespace(**{}),
        ]
        class E(dict):
            def get(self, k, d=None):
                return super().get(k, d)
        def mk(title, link):
            return E(title=title, link=link, published_parsed=NOW.timetuple())
        feed1 = [mk("Fed holds rates", "u1"), mk("Celebrity gossip", "u2")]
        feeds = (("F", "http://f", True), ("M", "http://m", False))
        with mock.patch.object(news, "fetch_feed", side_effect=lambda url: feed1):
            items, first = news.collect(state, NOW, feeds)
            self.assertTrue(first)
            self.assertEqual(items, [])           # أول تشغيل: تسجيل صامت
            feed1.append(mk("Powell speaks on inflation", "u3"))
            feed1.append(mk("Celebrity gossip 2", "u4"))
            items, first = news.collect(state, NOW, feeds)
        titles = [i["title"] for i in items]
        self.assertIn("Powell speaks on inflation", titles)
        self.assertNotIn("Celebrity gossip 2", [i["title"] for i in items if not i["official"]])
        with mock.patch.object(news, "fetch_feed", side_effect=lambda url: feed1):
            items, _ = news.collect(state, NOW, feeds)
        self.assertEqual(items, [])               # لا تكرار

    def test_stooq_parse_and_fallback(self):
        csv_ok = "Date,Open,High,Low,Close,Volume\n2026-10-22,1,1,1,3950,0\n2026-10-23,1,1,1,4000,0\n"
        with mock.patch.object(markets, "get", return_value=SimpleNamespace(text=csv_ok)):
            p, prev, asof = markets._stooq("xauusd")
        self.assertEqual((p, prev), (4000.0, 3950.0))
        bad = SimpleNamespace(text="Get your apikey")
        with mock.patch.object(markets, "get", return_value=bad):
            with self.assertRaises(RuntimeError):
                markets._stooq("xauusd")
        asset = ("gold", "Gold", "xauusd", "XAUUSD=X", 2)
        with mock.patch.dict(markets.PROVIDERS, {"stooq": (mock.Mock(side_effect=RuntimeError("x")), 2),
                                                "yahoo": (mock.Mock(return_value=(1.0, 0.5, "t")), 3)}):
            q, err = markets.fetch_quote(asset, ["stooq", "yahoo"])
        self.assertEqual((q.source, q.price), ("yahoo", 1.0))

    def test_secret_redaction(self):
        from econ_agent.http_utils import redact
        s = redact("https://api.telegram.org/bot123456:ABC-def_ghi/sendMessage?api_key=SECRET1")
        self.assertNotIn("ABC-def", s)
        self.assertNotIn("SECRET1", s)

    def test_health_alert_once_per_day(self):
        state = st.load("/nonexistent.json")
        for _ in range(config.HEALTH_FAIL_THRESHOLD):
            st.record(state, "fred", False, "boom")
        sent = []
        with mock.patch.object(main.telegram, "send", side_effect=sent.append):
            main.health_alerts(state)
            main.health_alerts(state)
        self.assertEqual(len(sent), 1)
        st.record(state, "fred", True)
        self.assertEqual(state["health"]["fred"]["fails"], 0)

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s", "state.json")
            s = st.load(p)
            s["sent"]["x"] = "2026-10-26"
            st.save(s, p)
            self.assertEqual(st.load(p)["sent"]["x"], "2026-10-26")

    def test_tick_end_to_end_dry_run(self):
        state = st.load("/nonexistent.json")
        q = markets.Quote("gold", "الذهب", 4000.0, 3950.0, "x", "stooq", 2)
        def obs(series, units="lin", limit=3):
            return [("2026-09-01", 1.0), ("2026-08-01", 0.9)]
        sent = []
        class FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW
        with mock.patch.object(main, "datetime", FakeDT), \
             mock.patch.object(fred, "observations", obs), \
             mock.patch.object(fred, "upcoming_dates", return_value=["2026-10-27"]), \
             mock.patch.object(markets, "fetch_all", return_value=({"gold": q}, {})), \
             mock.patch.object(news, "fetch_feed", return_value=[]), \
             mock.patch.object(main.telegram, "send", side_effect=sent.append):
            main.tick(state)
            self.assertEqual(len(sent), 1)           # التقرير الصباحي فقط
            self.assertIn("التقرير الاقتصادي الصباحي", sent[0])
            main.tick(state)
            self.assertEqual(len(sent), 1)           # لا تكرار في الجولة الثانية


if __name__ == "__main__":
    unittest.main()
