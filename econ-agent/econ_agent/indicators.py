"""تعريف المؤشرات. أضف مؤشرًا جديدًا بإضافة عنصر هنا فقط."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    series: str            # رمز السلسلة في FRED
    units: str = "lin"     # lin | pch (تغير % عن الفترة السابقة) | pc1 (% سنوي) | chg (تغير مطلق)
    decimals: int = 1
    suffix: str = ""
    hawkish_up: bool = True   # هل الارتفاع "صقري" (داعم للدولار/العوائد)؟
    tol: float = 0.0          # هامش اعتبار القراءة "مطابقة"
    analyze: bool = False     # هل تدخل في التحليل الآلي؟


@dataclass(frozen=True)
class Indicator:
    key: str
    name_ar: str
    metrics: tuple
    release_time_et: str = "08:30"
    trigger: str = "new_obs"   # new_obs: صدور قراءة جديدة | value_change: تغير القيمة فقط
    importance: str = "high"
    calendar: bool = True
    note: str = ""


INDICATORS = (
    Indicator("fed_rate", "سعر الفائدة الفيدرالي (نطاق الهدف)", (
        Metric("fed_upper", "الحد الأعلى", "DFEDTARU", decimals=2, suffix="%", tol=0.0, analyze=True),
        Metric("fed_lower", "الحد الأدنى", "DFEDTARL", decimals=2, suffix="%"),
    ), trigger="value_change", calendar=False),
    Indicator("cpi", "مؤشر أسعار المستهلكين CPI", (
        Metric("cpi_mom", "CPI شهريًا", "CPIAUCSL", "pch", 2, "%", tol=0.05, analyze=True),
        Metric("cpi_yoy", "CPI سنويًا", "CPIAUCSL", "pc1", 1, "%"),
        Metric("core_mom", "CPI الأساسي شهريًا", "CPILFESL", "pch", 2, "%", tol=0.05, analyze=True),
        Metric("core_yoy", "CPI الأساسي سنويًا", "CPILFESL", "pc1", 1, "%"),
    )),
    Indicator("nfp", "الوظائف غير الزراعية NFP والبطالة", (
        Metric("nfp", "التغير في الوظائف (آلاف)", "PAYEMS", "chg", 0, "K", tol=10, analyze=True),
        Metric("unrate", "معدل البطالة", "UNRATE", "lin", 1, "%", hawkish_up=False, tol=0.05, analyze=True),
    )),
    Indicator("gdp", "الناتج المحلي الإجمالي GDP (نمو فصلي سنوي معدّل)", (
        Metric("gdp", "نمو GDP الحقيقي", "A191RL1Q225SBEA", "lin", 1, "%", tol=0.1, analyze=True),
    ), note="قد تشمل التواريخ التقديرات الأولية والثانية والنهائية."),
    Indicator("sentiment", "ثقة المستهلك (جامعة ميشيغان)", (
        Metric("sentiment", "مؤشر ثقة المستهلك", "UMCSENT", "lin", 1, "", tol=1.0, analyze=True),
    ), release_time_et="10:00", importance="medium",
        note="مؤشر Conference Board غير متاح مجانًا عبر FRED."),
    Indicator("empire", "مؤشر إمباير ستيت للتصنيع (بديل جزئي لـ PMI)", (
        Metric("empire", "Empire State", "GACDISA066MSFRBNY", "lin", 1, "", tol=2.0, analyze=True),
    ), importance="medium", note="ليس PMI. مؤشر ISM / S&P Global PMI غير متاحين مجانًا عبر FRED."),
    Indicator("philly", "مؤشر فيلادلفيا الفيدرالي للتصنيع (بديل جزئي لـ PMI)", (
        Metric("philly", "Philly Fed", "GACDFSA066MSFRBPHI", "lin", 1, "", tol=2.0, analyze=True),
    ), importance="medium", note="ليس PMI."),
)

# بيانات سوقية يومية من FRED (تتأخر يومًا عادةً)
FRED_MARKET = (
    ("us02y", "عائد سندات الخزانة 2 سنوات", "DGS2"),
    ("us10y", "عائد سندات الخزانة 10 سنوات", "DGS10"),
    ("usd_broad", "مؤشر الدولار الواسع (Fed Broad)", "DTWEXBGS"),
)

# أصول الأسعار: رمز Stooq ورمز Yahoo لكل أصل (يُستخدم الأول المتاح)
ASSETS = (
    ("gold", "🥇 الذهب XAU/USD", "xauusd", "XAUUSD=X", 2),
    ("dxy", "💵 مؤشر الدولار DXY", "usdidx", "DX-Y.NYB", 2),
    ("eurusd", "EUR/USD", "eurusd", "EURUSD=X", 4),
    ("gbpusd", "GBP/USD", "gbpusd", "GBPUSD=X", 4),
    ("usdjpy", "USD/JPY", "usdjpy", "JPY=X", 2),
    ("usdchf", "USD/CHF", "usdchf", "CHF=X", 4),
    ("usdcad", "USD/CAD", "usdcad", "CAD=X", 4),
    ("spx", "📈 S&P 500", "^spx", "^GSPC", 2),
    ("ndq", "📈 Nasdaq Composite", "^ndq", "^IXIC", 2),
    ("dji", "📈 Dow Jones", "^dji", "^DJI", 2),
)

# مصادر الأخبار: (الاسم، الرابط، رسمي؟)
NEWS_FEEDS = (
    ("الاحتياطي الفيدرالي", "https://www.federalreserve.gov/feeds/press_all.xml", True),
    ("BLS", "https://www.bls.gov/feed/bls_latest.rss", True),
    ("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html", False),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", False),
)

NEWS_KEYWORDS = (
    "fed", "federal reserve", "powell", "fomc", "rate cut", "rate hike", "interest rate",
    "inflation", "cpi", "pce", "payroll", "jobs report", "unemployment", "gdp", "treasury",
    "yield", "gold", "dollar", "tariff", "recession", "retail sales", "pmi", "ism",
)
