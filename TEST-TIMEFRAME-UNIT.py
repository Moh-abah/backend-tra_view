# =============================================================================
# TEST-TIMEFRAME-UNIT.py — الجولة 13.3: اختبارات وحدة عقد الفريمات الموحد
# =============================================================================
# يُشغَّل مباشرة (بلا خادم): python3 TEST-TIMEFRAME-UNIT.py
# يثبت:
#   U-T1  فريم 1h يمنح شبكة ساعة فعلاً (فارق 3600000ms بين شمعتين متتاليتين)
#   U-T2  فريم 4h يمنح شبكة 4 ساعات فعلاً (فارق 14400000ms)
#   U-T3  فريم 15m يمنح شبكة ربع ساعة فعلاً (فارق 900000ms)
#   U-T4  فريم 2h (كان يسقط بصمت إلى 1h قبل الإصلاح) → شبكة ساعتين فعلاً
#   U-T5  فريم 1w → شبكة أسبوعية فعلاً (فارق 604800000ms)
#   U-T6  عملة ثانية (ETHUSDT) بفريم مختلف تعمل بنفس العقد
#   U-T7  فريم غير مدعوم ("45m") يُرفض برسالة صريحة تسرد المدعوم (لا صمت)
#   U-T8  فريم 1M يُرفض صراحة (شبكة تقويمية غير ثابتة) — موثق السبب
#   U-T9  السببية: آخر شمعة مغلقة فقط (آخر time + tf_ms <= end_ms)
# =============================================================================
import asyncio
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from app.providers.binance_provider import BinanceProvider, BINANCE_DIRECT_INTERVALS

PASS, FAIL = 0, 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name} {detail}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def _gaps_ms(times):
    """الفوارق الزمنية الفريدة بين شموع متتالية (ms)."""
    return sorted({int(times[i + 1] - times[i]) for i in range(len(times) - 1)})


async def fetch_grid(provider, symbol, timeframe, days, expect_ms, name):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    df = await provider.get_historicalcandl(symbol=symbol, timeframe=timeframe,
                                            start_date=start, end_date=end)
    if df.empty:
        # حظر مؤقت (418/429) — انتظار انتهاء التهدئة ثم محاولة واحدة أخيرة
        print(f"    ⏳ {name}: نافذة فارغة (حظر/تهدئة محتملة) — انتظار 310 ثانية وإعادة…")
        await asyncio.sleep(310)
        df = await provider.get_historicalcandl(symbol=symbol, timeframe=timeframe,
                                                start_date=start, end_date=end)
    assert not df.empty, f"{name}: no data returned (حتى بعد إعادة التهدئة)"
    times = df["time"].tolist()
    gaps = _gaps_ms(times)
    dominant = max(gaps, key=lambda g: sum(1 for i in range(len(times) - 1)
                                           if times[i + 1] - times[i] == g)) if gaps else 0
    ok(name, dominant == expect_ms,
       f"n={len(times)} · dominant_gap={dominant}ms (expected {expect_ms}ms) · "
       f"grid_gaps={gaps[:5]}")
    return df


async def main():
    p = BinanceProvider()

    # اختيار الحالات عبر argv (مثال: python3 TEST-TIMEFRAME-UNIT.py T4 T5 T6 T9)
    wanted = {a.upper() for a in sys.argv[1:]} or {"T1","T2","T3","T4","T5","T6","T7","T8","T9"}
    GAP = 70 if len(wanted & {"T4","T5","T6"}) > 1 else 8   # مباعدة احتراماً لحدود Binance

    print("\n=== U-T7/U-T8: الرفض الصريح (لا سقوط صامت — بلا شبكة إطلاقاً) ===")
    if "T7" in wanted:
        for bad, label in (("45m", "U-T7 · رفض 45m"),):
            try:
                await p.get_historicalcandl(symbol="BTCUSDT", timeframe=bad,
                                            start_date=datetime.now(timezone.utc) - timedelta(days=5),
                                            end_date=datetime.now(timezone.utc))
                ok(label, False, "لم يُرفض! (سقوط صامت ما زال حياً)")
            except ValueError as e:
                msg = str(e)
                ok(label, "Unsupported timeframe" in msg and "Supported" in msg,
                   f"ValueError صريحة: {msg[:110]}…")
    if "T8" in wanted:
        # "1M" (شهرية) تُرفض حساسياً — يجب ألا تسقط إلى "1m" دقيقة أبداً
        try:
            await p.get_historicalcandl(symbol="BTCUSDT", timeframe="1M",
                                        start_date=datetime.now(timezone.utc) - timedelta(days=5),
                                        end_date=datetime.now(timezone.utc))
            ok("U-T8 · رفض 1M", False, "لم يُرفض! (سقوط الشهرية إلى الدقيقة)")
        except ValueError as e:
            msg = str(e)
            ok("U-T8 · رفض 1M", "Unsupported timeframe" in msg,
               f"ValueError صريحة: {msg[:110]}…")

    if "T1" in wanted:
        print("\n=== U-T1..U-T6: شبكة كل فريم = الفريم المطلوب فعلاً ===")
        await asyncio.sleep(8)
        await fetch_grid(p, "BTCUSDT", "1h", 10, 3_600_000, "U-T1 · 1h شبكة ساعة")
        await asyncio.sleep(GAP)
    if "T2" in wanted:
        await fetch_grid(p, "BTCUSDT", "4h", 20, 14_400_000, "U-T2 · 4h شبكة 4 ساعات")
        await asyncio.sleep(GAP)
    if "T3" in wanted:
        await fetch_grid(p, "BTCUSDT", "15m", 3, 900_000, "U-T3 · 15m شبكة ربع ساعة")
        await asyncio.sleep(GAP)
    if "T4" in wanted:
        await fetch_grid(p, "BTCUSDT", "2h", 4, 7_200_000, "U-T4 · 2h شبكة ساعتين (كانت 1h زوراً)")
        await asyncio.sleep(GAP)
    if "T5" in wanted:
        await fetch_grid(p, "BTCUSDT", "1w", 90, 604_800_000, "U-T5 · 1w شبكة أسبوعية")
        await asyncio.sleep(GAP)
    if "T6" in wanted:
        await fetch_grid(p, "ETHUSDT", "6h", 5, 21_600_000, "U-T6 · ETHUSDT 6h شبكة 6 ساعات")
        await asyncio.sleep(GAP)

    if "T9" in wanted:
        print("\n=== U-T9: السببية — آخر شمعة مغلقة فقط ===")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=5)
        df = await p.get_historicalcandl(symbol="BTCUSDT", timeframe="4h",
                                         start_date=start, end_date=end)
        if df.empty:
            print("    ⏳ U-T9: نافذة فارغة (تهدئة) — انتظار 310 ثانية وإعادة…")
            await asyncio.sleep(310)
            df = await p.get_historicalcandl(symbol="BTCUSDT", timeframe="4h",
                                             start_date=start, end_date=end)
        tf_ms = 14_400_000
        last_open = int(df["time"].iloc[-1])
        ok("U-T9 · آخر شمعة مغلقة", last_open + tf_ms <= int(end.timestamp() * 1000) + 1,
           f"last_open+tf_ms <= end_ms · ({last_open}+{tf_ms} <= {int(end.timestamp()*1000)})")

    print("\n=== الفريمات المدعومة المعتمدة (عقد 13.3) ===")
    print(sorted(BINANCE_DIRECT_INTERVALS, key=p._timeframe_to_minutes))

    print(f"\n{'='*64}\n{'✅ ALL PASS' if FAIL == 0 else '❌ FAILURES'} — "
          f"pass={PASS} fail={FAIL}\n{'='*64}")
    sys.exit(0 if FAIL == 0 else 1)


asyncio.run(main())
