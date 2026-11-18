#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TS-FIX-1970 — حصن التحقق المحلي (الدوال الحقيقية من الشيفرة المُصلَحة).

يحاكي عطل الإنتاج #10000378 كاملاً (SOL 15m) ويتحقق من أن الطبقات الثلاث
تشفيه، وأن المسارات الجيدة بت-بت كما كانت (صفر انحدار).
"""
import sys
import types
import json
import importlib.util
import pandas as pd

# ---------------------------------------------------------------------------
# Stub البيئة (استيراد مستقل للملفات الحقيقية بلا قاعدة بيانات)
# ---------------------------------------------------------------------------
app = types.ModuleType("app"); app.__path__ = []
cfg = types.ModuleType("app.config")
class _S: pass
_s = _S()
for k, v in {"CANDLE_CACHE_MAX_CANDLES": 600000, "CANDLE_CACHE_ENABLED": True,
             "CANDLE_CACHE_DFSPACE": True, "CANDLE_CACHE_REFRESH_HEAD": True,
             "CANDLE_CACHE_GAP_TOLERANCE_MULT": 3,
             "CANDLE_CACHE_MAX_GAP_FETCHES": 6}.items():
    setattr(_s, k, v)
cfg.settings = _s
dbpkg = types.ModuleType("app.database"); dbpkg.__path__ = []
sess = types.ModuleType("app.database.session")
async def _wlr(fn, *a, **k):
    return await fn(*a, **k) if callable(fn) else None
sess.with_lock_retry = _wlr
sa = types.ModuleType("sqlalchemy")
for name in ("delete", "select", "update"):
    setattr(sa, name, lambda *a, **k: None)
# بذور حزم إضافية يحتاجها data_service عند الاستيراد (لا تُستخدم في دوالنا)
svc_pkg = types.ModuleType("app.services"); svc_pkg.__path__ = []
ind_mod = types.ModuleType("app.services.indicators")
ind_mod.apply_indicators = lambda **k: {}
ind_mod.calculate_trading_signals = lambda **k: {}
prov_pkg = types.ModuleType("app.providers"); prov_pkg.__path__ = []
bp_mod = types.ModuleType("app.providers.binance_provider")
class _BP:  # كعب موفّر بلا شبكة — الدوال المختبرة لا تلمسه
    def __init__(self, *a, **k): pass
bp_mod.BinanceProvider = _BP
usrp = types.ModuleType("app.providers.us_stock_provider")
usrp.USStockProvider = _BP
conv_mod = types.ModuleType("app.utils.converters")
conv_mod.TimeframeConverter = type("TimeframeConverter", (), {})
dbmod = types.ModuleType("app.database")
rc = types.ModuleType("app.database.redis_client")
rc.redis_client = None
fastapi_mod = types.ModuleType("fastapi")
fastapi_mod.HTTPException = type("HTTPException", (Exception,), {})
sqla_ext = types.ModuleType("sqlalchemy.ext.asyncio")
sqla_ext.AsyncSession = type("AsyncSession", (), {})
sys.modules.update({
    "app": app, "app.config": cfg, "app.database": dbpkg,
    "app.database.session": sess, "sqlalchemy": sa,
    "app.services": svc_pkg, "app.services.indicators": ind_mod,
    "app.providers": prov_pkg, "app.providers.binance_provider": bp_mod,
    "app.providers.us_stock_provider": usrp,
    "app.utils.converters": conv_mod,
    "app.database.redis_client": rc, "fastapi": fastapi_mod,
    "sqlalchemy.ext.asyncio": sqla_ext,
    "app.utils": types.ModuleType("app.utils"),
    "asyncpg": types.ModuleType("asyncpg"),
})

BASE = "/home/z/my-project/trading-system/project_extracted"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cc = load("cc", f"{BASE}/app/services/candle_cache.py")
ds = load("ds", f"{BASE}/app/services/data_service.py")

PASS, FAIL = [], []


def check(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
# عينة مرجعية: نافذة القاعدة 10000374 (SOL 15m — 2020-10-01 → 2021-03-09)
# ---------------------------------------------------------------------------
N = 15313
t0 = 1601510400000  # 2020-10-01T00:00:00Z بالمللي ثانية
STEP = 900_000       # 15 دقيقة
times = [t0 + i * STEP for i in range(N)]
good_df = pd.DataFrame({
    "time": pd.to_datetime(times, unit="ms", utc=True),
    "open": [2.0 + (i % 97) * 0.01 for i in range(N)],
    "high": [2.5 + (i % 97) * 0.01 for i in range(N)],
    "low": [1.9 + (i % 97) * 0.01 for i in range(N)],
    "close": [2.4 + (i % 97) * 0.01 for i in range(N)],
    "volume": [100.0 * (1 + (i % 53)) for i in range(N)],
})
good_df = good_df.set_index("time")  # نفس get_historical_last_version

print("=" * 70)
print("المحور 1 — الطبقة A: كاش redis الآمن للزمن (data_service)")
print("=" * 70)

# A1: الكتابة تحمل الزمن
payload = ds._range_cache_payload(good_df)
check("A1: الحمولة الجديدة تحمل عمود الزمن واسمه",
      payload is not None and payload.get("index_col") == "time"
      and all("time" in r for r in payload["records"][:5]))
check("A1b: القيم الزمنية epoch-ms مطابقة بت-بت",
      payload["records"][0]["time"] == t0
      and payload["records"][-1]["time"] == t0 + (N - 1) * STEP)

# A2: roundtrip JSON حقيقي (dumps/loads كما في redis_client) ثم إعادة البناء
blob = json.loads(json.dumps(payload))
rebuilt = ds._df_from_range_cache(blob)
check("A2: إعادة البناء تعيد فهرساً زمنياً DatetimeIndex",
      rebuilt is not None and isinstance(rebuilt.index, pd.DatetimeIndex))
check("A2b: الفهرس مطابق بت-بت للأصل (الاسم + القيم)",
      rebuilt.index.name == "time"
      and list(rebuilt.index.astype("int64")) == list(good_df.index.astype("int64"))
      and list(rebuilt.columns) == list(good_df.columns))
check("A2c: الأسعار مطابقة بت-بت",
      float(rebuilt["close"].iloc[0]) == float(good_df["close"].iloc[0])
      and float(rebuilt["close"].iloc[-1]) == float(good_df["close"].iloc[-1]))

# A3: الشكل القديم المسموم (قائمة بلا زمن — بصمة الإصدار السابق) ⇦ None
poisoned_legacy = good_df.to_dict("records")  # ← هذا ما كان يُخزَّن! (بلا زمن)
check("A3: المدخل القديم المسموم (بلا مفتاح زمني) يُرفض ⇦ None",
      ds._df_from_range_cache(poisoned_legacy) is None)

# A4: أعداد موضعية (0..n) كزمن ⇦ مرفوضة بدرس المعقولية
positional = [{"time": i, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 10.0}
              for i in range(100)]
check("A4: الطوابع الموضعية (0..n كأرقام) تُرفض — لا 1970 بعد اليوم",
      ds._df_from_range_cache(positional) is None)

# A5: إطار بلا فهرس زمني لا يُخزَّن أصلاً (منع السمّ من المنبع)
range_indexed = pd.DataFrame({"open": [1.0], "high": [1.1], "low": [0.9],
                              "close": [1.05], "volume": [10.0]})
check("A5: إطار بلا فهرس زمني ⇦ لا يُخزَّن (حمولة None)",
      ds._range_cache_payload(range_indexed) is None)

print()
print("=" * 70)
print("المحور 2 — الطبقة B: دروع مخطط كاش الشموع (candle_cache)")
print("=" * 70)

# B1: التقاط مخطط إطار بلا زمن ⇦ None (كان يُلتقط ويسمّم)
broken_df = pd.DataFrame({"open": [2.4, 2.5], "high": [2.6, 2.7],
                          "low": [2.0, 2.1], "close": [2.5, 2.6],
                          "volume": [200.0, 300.0]})
check("B1: _capture_df_schema يرفض الإطار بلا بعد زمني",
      cc._capture_df_schema(broken_df) is None)

# B2: الإطار الجيد (فهرس زمني) ⇦ مخطط سليم كما كان
good_schema = cc._capture_df_schema(good_df)
check("B2: الإطار الجيد (فهرس زمني) ⇦ مخطط سليم had_index=True",
      good_schema is not None and good_schema["had_index"]
      and good_schema["index_col"] == "time")

# B2b: إطار بعمود زمن (وضع الأيام) ⇦ مخطط سليم بعمود زمن
days_df = pd.DataFrame({"time": [t0, t0 + STEP], "open": [2.0, 2.1],
                        "high": [2.5, 2.6], "low": [1.9, 2.0],
                        "close": [2.4, 2.5], "volume": [100.0, 200.0]})
days_schema = cc._capture_df_schema(days_df)
check("B2b: إطار بعمود زمن (وضع الأيام) ⇦ مخطط مقبول بعمود زمن",
      days_schema is not None and "time" in days_schema["columns"])

# B3: إعادة بناء سجلات جيدة بمخطط مسموم ⇦ الزمن يُسترجَع (لا يُطرَد!)
good_records = cc._records_from_df(good_df)  # سجلات تحمل time كـ ISO
broken_schema = {
    "columns": ["open", "high", "low", "close", "volume"],
    "dtypes": {"open": "float64", "high": "float64", "low": "float64",
               "close": "float64", "volume": "float64"},
    "had_index": False, "index_col": None,
}
healed = cc._df_from_records(good_records[:50], broken_schema)
check("B3: مخطط مسموم + سجلات جيدة ⇦ الزمن يُسترجَع فهرساً (لا يُطرَد)",
      healed is not None and isinstance(healed.index, pd.DatetimeIndex)
      and str(healed.index[0]).startswith("2020-10-01"))

# B3b: القيم المسترجعة مطابقة بت-بت
orig_times = [r["time"] for r in good_records[:50]]
check("B3b: الطوابع المسترجعة بت-بت من السجلات",
      [t.isoformat() for t in healed.index] == orig_times)

# B4: المسار الجيد بت-بت (صفر انحدار): مخطط جيد + سجلات جيدة
rebuilt_good = cc._df_from_records(good_records, good_schema)
check("B4: المسار الجيد بلا انحدار — فهرس زمني بنفس الاسم والقيم",
      rebuilt_good is not None
      and isinstance(rebuilt_good.index, pd.DatetimeIndex)
      and rebuilt_good.index.name == good_df.index.name
      and list(rebuilt_good.index.astype("int64")) == list(good_df.index.astype("int64"))
      and list(rebuilt_good.columns) == list(good_df.columns))
check("B4b: dtypes كما كانت (float64)",
      str(rebuilt_good["open"].dtype) == "float64")

# B5: _schema_carries_time
check("B5: _schema_carries_time — جيد=True / مسموم=False",
      cc._schema_carries_time(good_schema) is True
      and cc._schema_carries_time(broken_schema) is False)

print()
print("=" * 70)
print("المحور 3 — الطبقة C: درع المحرك (engine1._normalize_candle_index)")
print("=" * 70)

# استخراج الدالة الثابتة من engine1 بلا استيراد الملف كاملاً (تبعياته ثقيلة)
import ast
src = open(f"{BASE}/app/backtest/engine1.py", encoding="utf-8").read()
tree = ast.parse(src)
fn_src = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "_normalize_candle_index":
        fn_src = ast.get_source_segment(src, node)
        break
assert fn_src, "_normalize_candle_index not found"
ns = {"pd": pd}
holder_src = "class _Holder:\n" + "\n".join("    " + ln for ln in fn_src.splitlines())
exec(compile(holder_src, "<holder>", "exec"), ns)
normalize = ns["_Holder"]._normalize_candle_index

# C1: فهرس زمني جيد ⇦ كما هو (صفر انحدار)
out = normalize(good_df)
check("C1: فهرس زمني جيد ⇦ يُعاد كما هو بت-بت",
      isinstance(out.index, pd.DatetimeIndex)
      and list(out.index.astype("int64")) == list(good_df.index.astype("int64")))

# C2: عمود time بالمللي ثانية (وضع الأيام القديم) ⇦ يُحوَّل كما كان
days_like = pd.DataFrame({"time": [t0, t0 + STEP], "open": [2.0, 2.1],
                          "high": [2.5, 2.6], "low": [1.9, 2.0],
                          "close": [2.4, 2.5], "volume": [100.0, 200.0]})
out2 = normalize(days_like)
check("C2: عمود time بالمللي ثانية ⇦ فهرس زمني (كما كان)",
      isinstance(out2.index, pd.DatetimeIndex)
      and "time" not in out2.columns
      and out2.index[0].isoformat().startswith("2020-10-01"))

# C3: فهرس رقمي 0..n (السمّ) ⇦ رفض صريح (كان يولّد 1970!)
poisoned_df = pd.DataFrame({"open": [2.0, 2.1], "high": [2.5, 2.6],
                            "low": [1.9, 2.0], "close": [2.4, 2.5],
                            "volume": [100.0, 200.0]})
try:
    normalize(poisoned_df)
    check("C3: الفهرس الرقمي الموضعي ⇦ يُرفض برفع صريح", False, "no exception raised")
except ValueError as e:
    check("C3: الفهرس الرقمي الموضعي ⇦ يُرفض برفع صريح",
          "TS-FIX-1970" in str(e), str(e)[:80])

# C4: تاريخ سلاسل في الفهرس (الحالة الأصلية المساندة) ⇦ يُحوَّل كما كان
str_idx = pd.DataFrame({"open": [1.0], "high": [1.1], "low": [0.9],
                        "close": [1.05], "volume": [10.0]},
                       index=pd.Index(["2020-10-01T00:00:00+00:00"], name="time"))
out4 = normalize(str_idx)
check("C4: فهرس سلاسل تواريخ ⇦ يُحوَّل لفهرس زمني (كما كان)",
      isinstance(out4.index, pd.DatetimeIndex))

print()
print("=" * 70)
print("المحور 4 — محاكاة عطل الإنتاج #10000378 كاملاً (الشفاء الشامل)")
print("=" * 70)

# السيناريو الحرفي: كاش redis مسموم يعيد إطاراً بلا زمن → المخطط الملتقط
# كان مسموماً → إعادة البناء كانت تطرد time → المحرك كان يولّد 1970.
print("  السيناريو: جلب من redis مسموم (بلا زمن) أثناء ملء الفجوات…")
poisoned_fetch_df = ds._df_from_range_cache(poisoned_legacy)  # الآن None
check("D1: جلب redis المسموم ⇦ يُعامل كإخفاق كاش (None = تجاوز للمزوّد)",
      poisoned_fetch_df is None)

print("  السيناريو: لو تسلّل مخطط مسموم قديم إلى إعادة البناء…")
schema_from_poison = cc._capture_df_schema(broken_df)  # الآن None
check("D2: التقاط مخطط من إطار مسموم ⇦ None (لا يُخزَّن ولا يتقدّم)",
      schema_from_poison is None)

print("  السيناريو: سجلات جيدة من مخزون القاعدة + مخطط مسموم قديم مخزَّن…")
healed2 = cc._df_from_records(good_records[:100], broken_schema)
check("D3: إعادة البناء تشفي — فهرس زمني حقيقي 2020 (لا 1970)",
      healed2 is not None and isinstance(healed2.index, pd.DatetimeIndex)
      and str(healed2.index[0]).startswith("2020-10-01")
      and str(healed2.index[-1]).startswith("2020-10-02")
      and int(healed2.index[-1].timestamp()) - int(healed2.index[0].timestamp()) == 99 * 900)

print("  السيناريو الحاسم: الناتج النهائي للمحرك بعد الشفاء…")
engine_in = healed2.copy()
ts_sec = [int(ts.timestamp()) for ts in engine_in.index]
check("D4: timestamps_sec للمحرك أزمنة حقيقية (≥ 2020) لا صفريّة",
      min(ts_sec) >= 1601510400 and max(ts_sec) >= min(ts_sec))

uniq = len(set(engine_in.index.astype("int64")))
check("D5: عدد الطوابع الفريدة = عدد الشموع (معيار القبول أ)",
      uniq == len(engine_in))

print()
print("=" * 70)
print(f"الخلاصة: {len(PASS)} PASS / {len(FAIL)} FAIL")
if FAIL:
    print("الفاشلات:", FAIL)
    sys.exit(1)
print("كل الحصون تعمل — الطوابع 1970 مستحيلة من كل الطرق الثلاثة.")
