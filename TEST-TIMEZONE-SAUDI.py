# -*- coding: utf-8 -*-
"""
TEST-TIMEZONE-SAUDI.py — الجولة 14.0: وحدات محاذاة التوقيت (السعودية UTC+3)

ما يثبته هذا الملف:
  T1  شمعة 1d بالتوقيت السعودي تفتح 21:00 UTC (= 00:00 مكة) وأرقامها = تجميع يدوي
  T2  شموع 4h السعودية: قاعدة الحدود (open+3h) % 4h == 0 + تطابق التجميع اليدوي
      + تكافؤ الأسس المختلفة (من 1h == من 2h)
  T3  الفريمات التي تقسم 3 ساعات (1m/3m/5m/10m/15m/30m/45m/1h/90m) حدودها
      لا تتغير إطلاقاً تحت +3h (مطابقة حرفية مع off=0)
  T4  1M السعودية: بداية الشهر 21:00 UTC لآخر يوم من الشهر السابق + الشهر
      الجاري يُسقط + تجميع يدوي مطابق
  T5  السببية: النافذة غير المكتملة تُسقط تحت الإزاحة أيضاً (لا repaint)
  T6  لا انحدار: off=0 مطابق حرفياً لتنفيذ الشبكة القديمة (قبل 14.0)
  T7  schemas: حلّ التوقيت (Asia/Riyadh=+180، UTC+3، رفض DST) + مواءمة
      التواريخ naive على جدار التوقيت المطلوب
  T8  الموزّع: 1h(+3h) مباشر · 4h/1d(+3h) إعادة تجميع مُزاحة · 1w(+3h) رفض
      · 45m(+3h) مطابق لـ off=0 · 1M(+3h) أشهر مزاحة · '2q' عقد رفض
  T9  تمرير الحقل عبر data_service → المزود (tz_offset_minutes يصل كما هو)
"""
import os
import sys
import types
import asyncio
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-local-verification-only-0123456789")
os.environ.setdefault("DEBUG", "true")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import pandas as pd  # noqa: E402

from app.providers.binance_provider import (  # noqa: E402
    BinanceProvider,
    resample_candles_to_minutes,
    resample_candles_to_month,
    pick_resample_base_interval,
)

H = 3_600_000
DAY = 86_400_000
SAUDI_OFF = 180  # UTC+3

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("PASS  " if cond else "FAIL  ") + name + ((" — " + detail) if detail else ""))
    return bool(cond)


def make_candles(interval_minutes: int, n: int, start_ms: int, seed: int = 7) -> pd.DataFrame:
    """شموع أساس اصطناعية منضبطة على شبكة Epoch (UTC)."""
    step = interval_minutes * 60_000
    rows = []
    p = 100.0
    for i in range(n):
        t = start_ms + i * step
        o = p
        c = p + ((i * seed) % 11) - 5
        h = max(o, c) + 1.5 + (i % 3)
        l = min(o, c) - 1.5 - ((i + 1) % 3)
        rows.append({"time": t, "open": float(o), "high": float(h),
                     "low": float(l), "close": float(c), "volume": float(10 + (i % 5))})
        p = c
    return pd.DataFrame(rows)


def manual_agg(df: pd.DataFrame, width_ms: int, off_ms: int, now_ms=None) -> pd.DataFrame:
    """تجميع مرجعي مستقل (يدوي) بنفس رياضيات الإزاحة — للتحقق المتقاطع."""
    out = df.copy()
    out["time"] = out["time"].astype("int64")
    out["_g"] = ((out["time"] + off_ms) // width_ms) * width_ms - off_ms
    rows = []
    for g, grp in out.groupby("_g", sort=True):
        rows.append({
            "time": int(g),
            "open": float(grp.sort_values("time")["open"].iloc[0]),
            "high": float(grp["high"].max()),
            "low": float(grp["low"].min()),
            "close": float(grp.sort_values("time")["close"].iloc[-1]),
            "volume": float(grp["volume"].sum()),
            "_n": len(grp),
        })
    res = pd.DataFrame(rows)
    if "_n" in res.columns and len(res):
        res = res[res["_n"] == (width_ms // (int(df["time"].diff().dropna().min()) or 1))]
    res = res.drop(columns=[c for c in ["_n"] if c in res.columns])
    if now_ms is not None and len(res):
        res = res[(res["time"] + width_ms) <= int(now_ms)]
    return res[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def frames_equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if a is None or b is None:
        return a is b
    if len(a) != len(b):
        return False
    if len(a) == 0:
        return True
    for c in ["time", "open", "high", "low", "close", "volume"]:
        if c not in a.columns or c not in b.columns:
            return False
        if not (a[c].astype(float).values == b[c].astype(float).values).all():
            return False
    return True


# ---------------------------------------------------------------------------
T0_START = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp() * 1000)

# T1 — 1d السعودية من أساس 1h (قاعدة straddle: 720∤180 فأساس 12h غير صالح):
# الافتتاح 21:00 UTC (= 00:00 مكة) + تطابق يدوي
base_1h_11d = make_candles(60, 24 * 11, T0_START)
r_1d_saudi = resample_candles_to_minutes(base_1h_11d, 1440, 60, now_ms=None, tz_offset_minutes=SAUDI_OFF)
opens_ok = all((int(t) + 3 * H) % DAY == 0 for t in r_1d_saudi["time"])
man_1d = manual_agg(base_1h_11d, DAY, 3 * H)
check("T1 1d-Saudi opens at 21:00 UTC (00:00 Riyadh)", opens_ok,
      f"first_open={datetime.fromtimestamp(int(r_1d_saudi['time'].iloc[0])/1000, tz=timezone.utc).isoformat()}")
check("T1 1d-Saudi OHLCV == manual aggregation", frames_equal(r_1d_saudi, man_1d),
      f"n={len(r_1d_saudi)}")
# وشمعة UTC القديمة تفتح 00:00 UTC — مختلفة عن السعودية
r_1d_utc = resample_candles_to_minutes(base_1h_11d, 1440, 60, now_ms=None, tz_offset_minutes=0)
check("T1 1d-UTC opens differ from 1d-Saudi",
      all(int(t) % DAY == 0 for t in r_1d_utc["time"]) and not frames_equal(r_1d_utc, r_1d_saudi))

# T2 — 4h السعودية من أساسين صحيحين (1h و30m — كلاهما يقسم 3h): تكافؤ + قاعدة الحدود + يدوي
# (الأساسان يُشتقّان من سلسلة 30m واحدة — سلسلة سعرية واحدة حقيقية)
base_30m = make_candles(30, 48 * 8, T0_START)          # 8 أيام
base_1h = resample_candles_to_minutes(base_30m, 60, 30, now_ms=None, tz_offset_minutes=0)
r_4h_from1h = resample_candles_to_minutes(base_1h, 240, 60, now_ms=None, tz_offset_minutes=SAUDI_OFF)
r_4h_from30m = resample_candles_to_minutes(base_30m, 240, 30, now_ms=None, tz_offset_minutes=SAUDI_OFF)
check("T2 4h-Saudi cross-base equivalence (from 1h == from 30m)", frames_equal(r_4h_from1h, r_4h_from30m))
check("T2 4h-Saudi boundary rule (open+3h)%4h==0",
      all((int(t) + 3 * H) % (4 * H) == 0 for t in r_4h_from1h["time"]),
      f"first_open={datetime.fromtimestamp(int(r_4h_from1h['time'].iloc[0])/1000, tz=timezone.utc).isoformat()}")
check("T2 4h-Saudi OHLCV == manual aggregation",
      frames_equal(r_4h_from1h, manual_agg(base_30m, 4 * H, 3 * H)))
# قاعدة الأساس: عرض الأساس يجب أن يقسم الإزاحة — أساس 2h مع +3h غير صالح (straddle)
base_2h_bad = resample_candles_to_minutes(base_30m, 120, 30, now_ms=None, tz_offset_minutes=0)
r_from_bad = resample_candles_to_minutes(base_2h_bad, 240, 120, now_ms=None, tz_offset_minutes=SAUDI_OFF)
check("T2 invalid base (2h, 180%120≠0) diverges → dispatcher must not pick it",
      not frames_equal(r_from_bad, r_4h_from1h))

# T3 — الفريمات التي تقسم 3 ساعات: حدودها لا تتغير تحت +3h
base_1m = make_candles(1, 2 * 1440, T0_START)  # يومان من الدقائق
all_same = True
for w in [1, 3, 5, 10, 15, 30, 45, 60, 90]:
    a = resample_candles_to_minutes(base_1m, w, 1, now_ms=None, tz_offset_minutes=0)
    b = resample_candles_to_minutes(base_1m, w, 1, now_ms=None, tz_offset_minutes=SAUDI_OFF)
    if not frames_equal(a, b):
        all_same = False
        print(f"      differs at width={w}m")
check("T3 widths dividing 3h are byte-identical under +3h", all_same,
      "widths: 1m,3m,5m,10m,15m,30m,45m,1h,90m")

# T4 — 1M السعودية: بداية الشهر 21:00 UTC + إسقاط الشهر الجاري + يدوي
# (مع إزاحة ≠ 0 الأساس الصحيح هو 1h — قاعدة straddle: 1d يعتدي على منتصف ليل الشهر المحلي)
JAN1 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
base_1h_60d = make_candles(60, 60 * 24, JAN1)  # يناير+فبراير 2026 (1440 شمعة ساعة)
# أساس اليوم يُشتق من نفس سلسلة الساعات (سلسلة سعرية واحدة — تكافؤ حقيقي)
base_1d_60 = resample_candles_to_minutes(base_1h_60d, 1440, 60, now_ms=None, tz_offset_minutes=0)
now_mar = int(datetime(2026, 3, 15, tzinfo=timezone.utc).timestamp() * 1000)
r_1m_saudi = resample_candles_to_month(base_1h_60d, now_ms=now_mar, tz_offset_minutes=SAUDI_OFF)
man_month = []
grp_map = {}
for _, row in base_1h_60d.iterrows():
    ym = pd.Timestamp(int(row["time"]) + 3 * H, unit="ms").strftime("%Y-%m")
    grp_map.setdefault(ym, []).append(row)
for ym in sorted(grp_map):
    rows = grp_map[ym]
    month_first_ms = int(datetime.strptime(ym, "%Y-%m").replace(tzinfo=timezone.utc).timestamp() * 1000) - 3 * H
    grp_map[ym] = {
        "time": month_first_ms,
        "open": float(rows[0]["open"]),
        "high": float(max(r["high"] for r in rows)),
        "low": float(min(r["low"] for r in rows)),
        "close": float(rows[-1]["close"]),
        "volume": float(sum(r["volume"] for r in rows)),
    }
expected_months = {ym: v for ym, v in grp_map.items() if ym in ("2026-01", "2026-02")}
ok_months = len(r_1m_saudi) == 2
if ok_months:
    for _, rrow in r_1m_saudi.iterrows():
        exp = expected_months.get(pd.Timestamp(int(rrow["time"]) + 3 * H, unit="ms").strftime("%Y-%m"))
        if exp is None or any(abs(float(rrow[c]) - exp[c]) > 1e-9 for c in ["time", "open", "high", "low", "close", "volume"]):
            ok_months = False
check("T4 1M-Saudi months (from 1h base) == manual (Jan/Feb only, current dropped)", ok_months,
      f"n={len(r_1m_saudi)}")
jan_open = datetime.fromtimestamp(int(r_1m_saudi["time"].iloc[0]) / 1000, tz=timezone.utc) if len(r_1m_saudi) else None
check("T4 1M-Saudi January opens 2025-12-31T21:00Z",
      jan_open is not None and jan_open.isoformat() == "2025-12-31T21:00:00+00:00",
      str(jan_open))
r_1m_utc = resample_candles_to_month(base_1d_60, now_ms=now_mar, tz_offset_minutes=0)
check("T4 1M-UTC opens differ from 1M-Saudi", not frames_equal(r_1m_utc, r_1m_saudi))
# UTC من 1h == UTC من 1d (تكافؤ الأسس الصحيحة عند off=0 — لا انحدار 13.4)
check("T4 1M-UTC from 1h == from 1d (no regression)",
      frames_equal(resample_candles_to_month(base_1h_60d, now_ms=now_mar, tz_offset_minutes=0), r_1m_utc))

# T5 — السببية: النافذة غير المكتملة تُسقط تحت الإزاحة
now_inside_last = T0_START + len(base_1h) * H - 2 * H  # داخل آخر نافذة 4h
r_causal = resample_candles_to_minutes(base_1h, 240, 60, now_ms=now_inside_last, tz_offset_minutes=SAUDI_OFF)
check("T5 incomplete last window dropped under shift",
      len(r_causal) > 0 and all((int(t) + 4 * H) <= now_inside_last for t in r_causal["time"]),
      f"now_ms={now_inside_last}, last_end={int(r_causal['time'].iloc[-1]) + 4 * H if len(r_causal) else None}")

# T6 — لا انحدار: off=0 == تنفيذ الشبكة القديمة حرفياً
def old_resample_minutes(df, n_minutes, base_minutes, now_ms=None):
    cols = ["time", "open", "high", "low", "close", "volume"]
    step = int(n_minutes) * 60_000
    expected = int(n_minutes) // int(base_minutes)
    out = df.copy()
    out["time"] = out["time"].astype("int64")
    grid = ((out["time"] // step) * step).rename("time")
    grouped = out.sort_values("time").groupby(grid, sort=True)
    res = grouped.agg({"open": "first", "high": "max", "low": "min",
                       "close": "last", "volume": "sum"}).reset_index()
    sizes = grouped.size().rename("_n").reset_index().rename(columns={"time": "time"})
    res = res.merge(sizes, on="time", how="left")
    keep = res["_n"] == expected
    if now_ms is not None:
        keep = keep & ((res["time"] + step) <= int(now_ms))
    return res[keep][cols].reset_index(drop=True)

check("T6 off=0 == pre-14.0 grid (4h from 1h)",
      frames_equal(resample_candles_to_minutes(base_1h, 240, 60, now_ms=None, tz_offset_minutes=0),
                   old_resample_minutes(base_1h, 240, 60)))
check("T6 off=0 == pre-14.0 grid (45m from 15m)",
      frames_equal(resample_candles_to_minutes(make_candles(15, 96 * 3, T0_START), 45, 15, now_ms=None, tz_offset_minutes=0),
                   old_resample_minutes(make_candles(15, 96 * 3, T0_START), 45, 15)))

# T7 — schemas: حلّ التوقيت + مواءمة التواريخ naive
from app.backtest.schemas import BacktestConfig, resolve_fixed_timezone_offset_minutes  # noqa: E402
check("T7 resolve Asia/Riyadh == +180", resolve_fixed_timezone_offset_minutes("Asia/Riyadh") == 180)
check("T7 resolve case-insensitive 'asia/RIYADH' == +180", resolve_fixed_timezone_offset_minutes("asia/RIYADH") == 180)
check("T7 resolve 'KSA' == +180", resolve_fixed_timezone_offset_minutes("KSA") == 180)
check("T7 resolve 'UTC' == 0", resolve_fixed_timezone_offset_minutes("UTC") == 0)
check("T7 resolve 'UTC+3' == +180", resolve_fixed_timezone_offset_minutes("UTC+3") == 180)
check("T7 resolve '+03:00' == +180", resolve_fixed_timezone_offset_minutes("+03:00") == 180)
check("T7 resolve 'Asia/Dubai' == +240", resolve_fixed_timezone_offset_minutes("Asia/Dubai") == 240)
check("T7 resolve 'UTC-05:30' == -330", resolve_fixed_timezone_offset_minutes("UTC-05:30") == -330)
try:
    resolve_fixed_timezone_offset_minutes("America/New_York")
    check("T7 reject DST zone 'America/New_York'", False)
except ValueError:
    check("T7 reject DST zone 'America/New_York'", True)

cfg = BacktestConfig(
    symbols=["BTCUSDT"], timeframe="1d", timezone="Asia/Riyadh",
    start_date=datetime(2026, 10, 1), end_date=datetime(2026, 11, 1),
)
check("T7 config.tz_offset_minutes == 180", cfg.tz_offset_minutes == 180)
check("T7 naive dates aligned on Riyadh wall (start → 2026-09-30T21:00Z)",
      cfg.start_date == datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc), cfg.start_date.isoformat())
check("T7 naive dates aligned on Riyadh wall (end → 2026-10-31T21:00Z)",
      cfg.end_date == datetime(2026, 10, 31, 21, 0, tzinfo=timezone.utc), cfg.end_date.isoformat())
cfg_utc = BacktestConfig(symbols=["BTCUSDT"], timeframe="1d",
                         start_date=datetime(2026, 10, 1), end_date=datetime(2026, 11, 1))
check("T7 default timezone is UTC (no regression)", cfg_utc.tz_offset_minutes == 0
      and cfg_utc.start_date == datetime(2026, 10, 1, tzinfo=timezone.utc))

# T8 — الموزّع: توجيه المسارات تحت الإزاحة (native مُرقّع بلا شبكة)
async def t8():
    prov = BinanceProvider.__new__(BinanceProvider)
    calls = []

    async def fake_native(symbol, timeframe, start_date, end_date=None):
        calls.append(timeframe)
        mins = {"1m": 1, "15m": 15, "1h": 60, "2h": 120, "4h": 240, "12h": 720, "1d": 1440, "1w": 10080}[timeframe]
        # نحاكي سلوك المسار الأصلي الحقيقي: أرضية البداية على شبكة الفريم
        t0 = int(start_date.timestamp() * 1000)
        t0 = (t0 // (mins * 60_000)) * (mins * 60_000)
        n = max(4, int((end_date.timestamp() * 1000 - t0) // (mins * 60_000)) + 2)
        return make_candles(mins, n, t0)

    prov._get_historical_native = fake_native
    s = datetime(2026, 10, 1, tzinfo=timezone.utc)
    e = datetime(2026, 10, 11, tzinfo=timezone.utc)

    # 1h + إزاحة → جلب مباشر (حدود لا تتغير)
    calls.clear()
    await prov.get_historicalcandl("BTCUSDT", "1h", s, e, tz_offset_minutes=SAUDI_OFF)
    check("T8 1h(+3h) stays native-direct", calls == ["1h"], str(calls))

    # 4h + إزاحة → إعادة تجميع مُزاحة من 1h (وليس 2h — 180%120≠0 straddle)
    calls.clear()
    r = await prov.get_historicalcandl("BTCUSDT", "4h", s, e, tz_offset_minutes=SAUDI_OFF)
    check("T8 4h(+3h) resamples from 1h base (straddle-safe picker)", "1h" in calls and "4h" not in calls, str(calls))
    check("T8 4h(+3h) boundary rule", all((int(t) + 3 * H) % (4 * H) == 0 for t in r["time"]))

    # 2h و8h و12h + إزاحة → كلها من 1h
    for tf_name in ["2h", "8h", "12h"]:
        calls.clear()
        await prov.get_historicalcandl("BTCUSDT", tf_name, s, e, tz_offset_minutes=SAUDI_OFF)
        check(f"T8 {tf_name}(+3h) resamples from 1h base", "1h" in calls and tf_name not in calls, str(calls))

    # 1d + إزاحة → إعادة تجميع مُزاحة من 1h والافتتاح 21:00 UTC
    calls.clear()
    r = await prov.get_historicalcandl("BTCUSDT", "1d", s, e, tz_offset_minutes=SAUDI_OFF)
    check("T8 1d(+3h) resamples from 1h base", "1h" in calls and "1d" not in calls, str(calls))
    check("T8 1d(+3h) opens at 21:00 UTC", all((int(t) + 3 * H) % DAY == 0 for t in r["time"]),
          f"first={datetime.fromtimestamp(int(r['time'].iloc[0])/1000, tz=timezone.utc).isoformat()}")

    # 1w + إزاحة → رفض صريح
    try:
        await prov.get_historicalcandl("BTCUSDT", "1w", s, e, tz_offset_minutes=SAUDI_OFF)
        check("T8 1w(+3h) rejected", False)
    except ValueError as ex:
        check("T8 1w(+3h) rejected with clear contract", "not supported" in str(ex))

    # 1w بدون إزاحة → مباشر (لا انحدار)
    calls.clear()
    await prov.get_historicalcandl("BTCUSDT", "1w", s, e, tz_offset_minutes=0)
    check("T8 1w(UTC) stays native-direct (no regression)", calls == ["1w"], str(calls))

    # 45m + إزاحة → من 15m ومطابق حرفياً لـ off=0 (180%45==0)
    calls.clear()
    r45_shift = await prov.get_historicalcandl("BTCUSDT", "45m", s, e, tz_offset_minutes=SAUDI_OFF)
    check("T8 45m(+3h) resamples from 15m", "15m" in calls, str(calls))
    r45_utc = await prov.get_historicalcandl("BTCUSDT", "45m", s, e, tz_offset_minutes=0)
    check("T8 45m(+3h) identical to 45m(UTC)", frames_equal(r45_shift, r45_utc),
          f"n={len(r45_shift)}")

    # 1M + إزاحة → من 1d وبداية الشهر 21:00 UTC
    # (نافذة تمتد لشهرين: الشهر الجاري يُسقط سببياً ويبقى الشهر المكتمل)
    calls.clear()
    rm = await prov.get_historicalcandl(
        "BTCUSDT", "1M",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 11, tzinfo=timezone.utc),
        tz_offset_minutes=SAUDI_OFF,
    )
    check("T8 1M(+3h) resamples from 1h base (straddle-safe)", "1h" in calls and "1d" not in calls, str(calls))
    sep_opens_ok = len(rm) > 0 and all((int(t) + 3 * H) % DAY == 0 for t in rm["time"])
    sep_open = datetime.fromtimestamp(int(rm["time"].iloc[-1]) / 1000, tz=timezone.utc) if len(rm) else None
    check("T8 1M(+3h) month opens at 21:00 UTC (September → 2026-08-31T21:00Z)",
          sep_opens_ok and sep_open is not None and sep_open.isoformat() == "2026-08-31T21:00:00+00:00",
          f"n={len(rm)} last_open={sep_open}")

    # فريم غير صالح → عقد الرفض
    try:
        await prov.get_historicalcandl("BTCUSDT", "2q", s, e, tz_offset_minutes=SAUDI_OFF)
        check("T8 '2q' rejected by contract", False)
    except ValueError as ex:
        check("T8 '2q' rejected by contract", "Unsupported timeframe" in str(ex))

asyncio.run(t8())

# T9 — تمرير tz_offset_minutes عبر data_service → المزود (بوحدات معزولة)
def t9():
    fake_fastapi = types.ModuleType("fastapi")
    fake_fastapi.HTTPException = type("HTTPException", (Exception,), {})
    sys.modules.setdefault("fastapi", fake_fastapi)
    for name in ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio"):
        sys.modules.pop(name, None)
    sa = types.ModuleType("sqlalchemy")
    ext = types.ModuleType("sqlalchemy.ext")
    aio_m = types.ModuleType("sqlalchemy.ext.asyncio")
    aio_m.AsyncSession = object
    sa.ext = ext
    ext.asyncio = aio_m
    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.ext"] = ext
    sys.modules["sqlalchemy.ext.asyncio"] = aio_m
    rc = types.ModuleType("app.database.redis_client")

    class _RC:
        async def get_cached(self, k):
            return None

        async def set_cached(self, k, v, ttl=None):
            return True

    rc.redis_client = _RC()
    sys.modules["app.database.redis_client"] = rc
    ind = types.ModuleType("app.services.indicators")
    ind.apply_indicators = lambda df, *a, **k: df
    ind.calculate_trading_signals = lambda *a, **k: {}
    sys.modules["app.services.indicators"] = ind

    from app.services.data_service import DataService

    received = {}

    class FakeProvider:
        async def get_historicalcandl(self, **kwargs):
            received.update(kwargs)
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    ds = DataService.__new__(DataService)
    ds.providers = {"crypto": FakeProvider()}
    s = datetime(2026, 10, 1, tzinfo=timezone.utc)
    e = datetime(2026, 10, 11, tzinfo=timezone.utc)
    asyncio.run(ds.get_historical_last_version(
        symbol="BTCUSDT", timeframe="1d", market="crypto",
        start_date=s, end_date=e, use_cache=False, tz_offset_minutes=180,
    ))
    check("T9 data_service forwards tz_offset_minutes=180 to provider",
          received.get("tz_offset_minutes") == 180, str(received.get("tz_offset_minutes")))

t9()

# ---------------------------------------------------------------------------
failed = [n for n, ok, _ in RESULTS if not ok]
print()
print(f"TOTAL={len(RESULTS)} PASS={len(RESULTS) - len(failed)} FAIL={len(failed)}")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("ALL-PASS")
