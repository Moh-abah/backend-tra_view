# -*- coding: utf-8 -*-
"""
VERIFY-TIMEZONE-SAUDI.py — الجولة 14.0: إثبات حي ببيانات Binance الحقيقية
أن التوقيت السعودي (Asia/Riyadh = UTC+3) يعمل عبر الموزّع الفعلي.

  L1  1d حقيقية: UTC يفتح 00:00Z · السعودية تفتح 21:00Z (= 00:00 مكة)
  L2  1d السعودية == تجميع يدوي من شموع 1h حقيقية (تكافؤ المسار الموزّع/المباشر)
      و1d UTC == تجميع يدوي off=0 (لا انحدار على بيانات حقيقية)
  L3  4h السعودية == تجميع يدوي من 1h حقيقية + قاعدة الحدود (open+3h)%4h==0
  L4  1h حقيقية: UTC == السعودية حرفياً (الإزاحة لا تغيّر حدود ≤ 3h)
  L5  15m حقيقية: UTC == السعودية حرفياً
  L6  1M حقيقية: UTC يفتح 00:00Z لليوم الأول · السعودية 21:00Z لآخر يوم الشهر السابق
  L7  '1w' مع إزاحة → رفض عقد نظيف
  L8  45m حقيقية: UTC == السعودية حرفياً (180%45==0)
"""
import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "verify-secret-key-local-0123456789abcdef")
os.environ.setdefault("DEBUG", "true")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import pandas as pd  # noqa: E402
import app.providers.binance_provider as _bp  # noqa: E402
from app.providers.binance_provider import (  # noqa: E402
    BinanceProvider, resample_candles_to_minutes, resample_candles_to_month,
)

H = 3_600_000
DAY = 86_400_000
OFF = 180  # UTC+3 السعودية

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("PASS  " if cond else "FAIL  ") + name + ((" — " + detail) if detail else ""))


def iso(ms):
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


def frames_equal(a, b, rtol=1e-9):
    """مطابقة بتسامح نسبي: OHLC متطابقة حرفياً، والفوليوم المجمّع من شموع
    أصغر قد يختلف في آخر ulp عائم عن سجلات Binance المبنية من الصفقات —
    1e-9 نسبي يلتقط أي خطأ حقيقي ويسمح بهذا الاختلاف العائم المتأصل."""
    if a is None or b is None or len(a) != len(b):
        return False
    if len(a) == 0:
        return True
    import numpy as np
    for c in ["time", "open", "high", "low", "close", "volume"]:
        va = a[c].astype(float).values
        vb = b[c].astype(float).values
        if not (abs(va - vb) <= rtol * np.maximum(1.0, abs(vb))).all():
            return False
    return True


async def fetch_with_retry(prov, symbol, tf, start, end, off, attempts=4):
    """جلب مع صبر على الحظر المؤقت (418/429) + تراجع لمرآة data-api.binance.vision.

    يرفض الإطارات الموسومة fetch_incomplete (دفعة فشلت) — إعادة الطلب تملأ
    الفجوات من الكاش (سلوك 13.4 الموثق) حتى تكتمل النافذة.
    (في سكربت التحقق فقط: نصفر قاطع التهدئة العام بين المحاولات حتى لا
    تحجب فترة 300s كل محاولاتنا — الإنتاج لا يفعل ذلك).
    """
    last_err = None
    for i in range(attempts):
        df = await prov.get_historicalcandl(symbol, tf, start, end, tz_offset_minutes=off)
        if df is not None and not df.empty and not bool(df.attrs.get("fetch_incomplete")):
            return df
        # نافذة فارغة/ناقصة = حظر أو فشل دفعات — بدّل المرآة وانتظر ثم أعد
        prov.base_url = "https://data-api.binance.vision"
        last_err = f"attempt {i + 1}: empty={df is None or df.empty} incomplete={bool(df is not None and df.attrs.get('fetch_incomplete'))}"
        print(f"   … retry {i + 1}/{attempts} for {tf} off={off} ({last_err})")
        _bp._BAN_STATE["until"] = 0.0
        _bp._BAN_STATE["reason"] = ""
        await asyncio.sleep([40, 75, 100, 120][min(i, 3)])
    raise RuntimeError(f"fetch failed for {symbol} {tf} off={off}: {last_err} "
                      "(Binance IP ban window — أعد تشغيل السكربت بعد انتهاء الحظر)")


async def main():
    prov = BinanceProvider()
    # ✅ مرآة بيانات السوق الرسمية — تُستخدم مباشرة عند حظر IP الرئيسي (418):
    # BINANCE_USE_VISION=1 python3 VERIFY-TIMEZONE-SAUDI.py
    if os.environ.get("BINANCE_USE_VISION") == "1":
        prov.base_url = "https://data-api.binance.vision"
        print("ℹ️ using official market-data mirror: data-api.binance.vision")
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=30)

    # ---- L1: 1d UTC مقابل 1d السعودية (نافذة 30 يوماً) ----
    d_utc = await fetch_with_retry(prov, "BTCUSDT", "1d", start, end, 0)
    await asyncio.sleep(1.0)
    d_saudi = await fetch_with_retry(prov, "BTCUSDT", "1d", start, end, OFF)
    check("L1 1d-UTC opens at 00:00Z", len(d_utc) > 0 and all(int(t) % DAY == 0 for t in d_utc["time"]),
          f"n={len(d_utc)} first={iso(d_utc['time'].iloc[0])}")
    check("L1 1d-Saudi opens at 21:00Z (00:00 Riyadh)",
          len(d_saudi) > 0 and all((int(t) + 3 * H) % DAY == 0 for t in d_saudi["time"]),
          f"n={len(d_saudi)} first={iso(d_saudi['time'].iloc[0])}")
    check("L1 1d counts match (±1 window)", abs(len(d_utc) - len(d_saudi)) <= 1,
          f"utc={len(d_utc)} saudi={len(d_saudi)}")

    # ---- L2: تكافؤ يدوي من 1h حقيقية ----
    # (الأرضية اليدوية مطابقة لمنطق المزوّد: أرضية البداية على الشبكة المزاحة
    #  حتى تكون أول نافذة كاملة — وإلا فالمرجع اليدوي يفقد ساعات بدايته)
    start_ms = int(start.timestamp() * 1000)
    day_floored_ms = ((start_ms + 3 * H) // DAY) * DAY - 3 * H
    h_floored = await fetch_with_retry(prov, "BTCUSDT", "1h",
                                       datetime.fromtimestamp(day_floored_ms / 1000, tz=timezone.utc), end, 0)
    man_saudi = resample_candles_to_minutes(h_floored, 1440, 60, now_ms=int(end.timestamp() * 1000), tz_offset_minutes=OFF)
    man_utc = resample_candles_to_minutes(h_floored, 1440, 60, now_ms=int(end.timestamp() * 1000), tz_offset_minutes=0)
    check("L2 1d-Saudi(provider) == manual-from-1h(offset=180)", frames_equal(d_saudi, man_saudi),
          f"provider={len(d_saudi)} manual={len(man_saudi)}")
    check("L2 1d-UTC(provider) == manual-from-1h(offset=0) — no regression",
          frames_equal(d_utc, man_utc), f"provider={len(d_utc)} manual={len(man_utc)}")
    # تحقق قيمة يدوية صريحة: شمعة اليوم السعودي الأولى
    if len(d_saudi) and len(h_floored):
        w0 = int(d_saudi["time"].iloc[0])
        grp = h_floored[(h_floored["time"] >= w0) & (h_floored["time"] < w0 + DAY)]
        ok_o = abs(float(grp["open"].iloc[0]) - float(d_saudi["open"].iloc[0])) < 1e-9
        ok_h = abs(float(grp["high"].max()) - float(d_saudi["high"].iloc[0])) < 1e-9
        ok_l = abs(float(grp["low"].min()) - float(d_saudi["low"].iloc[0])) < 1e-9
        ok_c = abs(float(grp.sort_values("time")["close"].iloc[-1]) - float(d_saudi["close"].iloc[0])) < 1e-9
        ok_v = abs(float(grp["volume"].sum()) - float(d_saudi["volume"].iloc[0])) < 1e-9
        check("L2 first Saudi daily candle OHLCV == union of its 24 hourly candles (1e-9)",
              ok_o and ok_h and ok_l and ok_c and ok_v,
              f"window={iso(w0)}..{iso(w0 + DAY)} candles={len(grp)}")

    # ---- L3: 4h السعودية == يدوي من 1h + قاعدة الحدود ----
    h4 = await fetch_with_retry(prov, "BTCUSDT", "4h", start, end, OFF)
    fourh_floored_ms = ((start_ms + 3 * H) // (4 * H)) * (4 * H) - 3 * H
    h4_base = await fetch_with_retry(prov, "BTCUSDT", "1h",
                                     datetime.fromtimestamp(fourh_floored_ms / 1000, tz=timezone.utc), end, 0)
    man4 = resample_candles_to_minutes(h4_base, 240, 60, now_ms=int(end.timestamp() * 1000), tz_offset_minutes=OFF)
    check("L3 4h-Saudi(provider) == manual-from-1h", frames_equal(h4, man4),
          f"n={len(h4)}")
    check("L3 4h-Saudi boundary rule (open+3h)%4h==0",
          len(h4) > 0 and all((int(t) + 3 * H) % (4 * H) == 0 for t in h4["time"]),
          f"first={iso(h4['time'].iloc[0])} (= {iso(int(h4['time'].iloc[0]) + 3*H)} Riyadh)")

    # ---- L4/L5: 1h و15m — الإزاحة لا تغيّر شيئاً ----
    h1_saudi = await fetch_with_retry(prov, "BTCUSDT", "1h",
                                      datetime.fromtimestamp(day_floored_ms / 1000, tz=timezone.utc), end, OFF)
    check("L4 1h-UTC == 1h-Saudi (identical frames)", frames_equal(h_floored, h1_saudi),
          f"n={len(h_floored)}")
    m_start = end - timedelta(days=2)
    await asyncio.sleep(1.0)
    m_utc = await fetch_with_retry(prov, "BTCUSDT", "15m", m_start, end, 0)
    await asyncio.sleep(1.0)
    m_saudi = await fetch_with_retry(prov, "BTCUSDT", "15m", m_start, end, OFF)
    check("L5 15m-UTC == 15m-Saudi (identical frames)", frames_equal(m_utc, m_saudi),
          f"n={len(m_utc)}")

    # ---- L6: 1M حقيقية (بداية الشهر البعيد على حدّ شهر UTC — تغطية متطابقة) ----
    now_dt = end
    mm_start = datetime(now_dt.year, now_dt.month, 1, tzinfo=timezone.utc) - timedelta(days=95)
    mm_start = datetime(mm_start.year, mm_start.month, 1, tzinfo=timezone.utc)
    await asyncio.sleep(1.0)
    mm_utc = await fetch_with_retry(prov, "BTCUSDT", "1M", mm_start, end, 0)
    await asyncio.sleep(1.0)
    mm_saudi = await fetch_with_retry(prov, "BTCUSDT", "1M", mm_start, end, OFF)
    check("L6 1M-UTC opens at first-day 00:00Z",
          len(mm_utc) > 0 and all(int(t) % DAY == 0 for t in mm_utc["time"]),
          f"n={len(mm_utc)} first={iso(mm_utc['time'].iloc[0])}")
    check("L6 1M-Saudi opens at 21:00Z (Riyadh month start)",
          len(mm_saudi) > 0 and all((int(t) + 3 * H) % DAY == 0 for t in mm_saudi["time"]),
          f"n={len(mm_saudi)} first={iso(mm_saudi['time'].iloc[0])}")
    check("L6 1M month counts equal", len(mm_utc) == len(mm_saudi),
          f"utc={len(mm_utc)} saudi={len(mm_saudi)}")
    # L6b — إثبات المحتوى: الشهور السعودية == تجميع يدوي مباشر من شموع 1h حقيقية
    # (أرضية يدوية مطابقة للموزّع: بداية الأساس = حد الشهر السعودي — Jun30 21:00Z مثلاً)
    s_shifted = mm_start + timedelta(minutes=OFF)
    month_floored = datetime(s_shifted.year, s_shifted.month, 1, tzinfo=timezone.utc) - timedelta(minutes=OFF)
    h_for_months = await fetch_with_retry(prov, "BTCUSDT", "1h", month_floored, end, 0)
    man_mm_saudi = resample_candles_to_month(
        h_for_months, now_ms=int(end.timestamp() * 1000), tz_offset_minutes=OFF)
    check("L6b 1M-Saudi(provider) == manual-from-1h(offset=180)",
          frames_equal(mm_saudi, man_mm_saudi),
          f"provider={len(mm_saudi)} manual={len(man_mm_saudi)}")

    # ---- L7: 1w + إزاحة → رفض نظيف (لا شبكة) ----
    try:
        await prov.get_historicalcandl("BTCUSDT", "1w", start, end, tz_offset_minutes=OFF)
        check("L7 1w(+3h) rejected", False)
    except ValueError as ex:
        check("L7 1w(+3h) rejected with clear contract", "not supported" in str(ex))

    # ---- L8: 45m حقيقية — مطابقة تامة بين التوقيتين ----
    await asyncio.sleep(1.0)
    r45_utc = await fetch_with_retry(prov, "BTCUSDT", "45m", m_start, end, 0)
    await asyncio.sleep(1.0)
    r45_saudi = await fetch_with_retry(prov, "BTCUSDT", "45m", m_start, end, OFF)
    check("L8 45m-UTC == 45m-Saudi (180%45==0 → identical)", frames_equal(r45_utc, r45_saudi),
          f"n={len(r45_utc)}")

    print()
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"TOTAL={len(RESULTS)} PASS={len(RESULTS) - len(failed)} FAIL={len(failed)}")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("ALL-PASS-LIVE")


asyncio.run(main())
