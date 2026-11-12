# verify_r61_acceptance.py
"""✅ R61 — اختبارات القبول الحقيقية لإصلاح فجوة كاش الشموع (Binance حي).

يشغّل المسار الإنتاجي نفسه بت-بت: BacktestEngine ⇠ CachedDataService ⇠
CandleCacheService (المُصلَّح) ⇠ DataService ⇠ BinanceProvider — على SQLite
محلية، مع كاش Parquet الحقيقي — فيغطي:

  A  عبّئ كاش BTCUSDT بنافذة يومين فقط (طلب 2d·1m) ثم اطلب 30d·1m فوراً
     ⇦ المتوقع: coverage_pct=100.0 · delivered ≈ 43,200 · gap_filled=true
  D  أعد بناء مخزون #10000098 المتضرر حرفياً (شظية قديمة قبل النافذة +
     ذيل قرب نهايتها وفراغ بينهما) ثم شغّل حمولة #10000098 نفسها عبر
     المحرك دون حذف الكاش ⇦ المتوقع: نفس نتيجة #10000099
     (43,200 شمعة · 9 صفقات · ‎-2.06%)
  C  SOLUSDT · 1m · 477d: جلب بارد ثم طلب دافئ فوري
     ⇦ المتوقع: التسليم يبقى ~686,880+ مدموجة (لا تفشّط) والتغطية 100%
  B  مفتاح SOLUSDT لا يحوي إلا أسابيع (21d) ثم طلب 365d·1m
     ⇦ المتوقع: جلب الفجوة البادئة ≈ 525,600 · coverage 100 · gap_filled

التشغيل:  python3 verify_r61_acceptance.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time as _time

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB = os.path.join(_HERE, "r61_e2e.db")
if os.path.exists(_DB):
    os.remove(_DB)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ.setdefault("CANDLE_CACHE_GAP_TOLERANCE_MULT", "3")
sys.path.insert(0, _HERE)

PASS, FAIL = [], []
T0 = _time.perf_counter()


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    mark = "✅" if cond else "❌"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""), flush=True)


def banner(txt: str) -> None:
    print("\n" + "━" * 72 + f"\n{txt}\n" + "━" * 72, flush=True)


def card_line(meta: dict) -> str:
    c = meta.get("cache") or {}
    return (
        f"hit={c.get('hit')} delivered={c.get('delivered_candles')}"
        f"/{c.get('expected_candles')} coverage={c.get('coverage_pct')}%"
        f" gaps={c.get('gaps_detected')}→{c.get('gaps_remaining')}"
        f" natural={c.get('natural_gaps')} fills={c.get('fill_calls')}"
        f" fetched_new={c.get('fetched_new')} incomplete={c.get('fetch_incomplete')}"
    )


async def make_services(session_maker):
    from app.services.data_service import DataService
    from app.services.candle_cache import CachedDataService

    ds = DataService(None)
    cached = CachedDataService(ds, session_maker=session_maker)
    return ds, cached


async def range_fetch_via_cache(cached, symbol, timeframe, market, s_ts, e_ts, tz_off=0):
    """طلب نافذة عبر نفس واجهة المحرك (get_historical_last_version)."""
    from datetime import datetime, timezone as _tz

    df = await cached.get_historical_last_version(
        symbol=symbol, timeframe=timeframe, market=market,
        start_date=datetime.fromtimestamp(int(s_ts), tz=_tz.utc),
        end_date=datetime.fromtimestamp(int(e_ts), tz=_tz.utc),
        use_cache=True, tz_offset_minutes=tz_off,
    )
    return df


async def test_a(session_maker, sm):
    banner("اختبار القبول A · BTCUSDT: كاش يومين فقط ثم طلب 30d·1m")
    from datetime import datetime, timezone as _tz

    now = int(_time.time())
    _, cached = await make_services(session_maker)

    # 1) نافذة يومين (تعبئة الكاش)
    df2 = await range_fetch_via_cache(cached, "BTCUSDT", "1m", "crypto", now - 2 * 86400, now)
    m1 = dict(cached.last_meta or {})
    print(f"  [تعبئة 2d] {card_line(m1)}")
    check("A/1 التعبئة نفذت", df2 is not None and len(df2) > 2_700,
          f"rows={0 if df2 is None else len(df2)}")

    # 2) طلب 30d فوراً — الخلل القديم كان يعطي ~2,880 فقط
    df30 = await range_fetch_via_cache(cached, "BTCUSDT", "1m", "crypto", now - 30 * 86400, now)
    m2 = dict(cached.last_meta or {})
    c = m2.get("cache") or {}
    print(f"  [طلب 30d] {card_line(m2)}")
    print(f"  note: {c.get('note')}")
    check("A/2 coverage_pct == 100.0", c.get("coverage_pct") == 100.0,
          f"coverage={c.get('coverage_pct')}")
    check("A/3 delivered ≈ 43,200", 43_100 <= int(c.get("delivered_candles") or 0) <= 43_210,
          f"delivered={c.get('delivered_candles')}")
    check("A/4 gap_filled == true", c.get("gap_filled") is True)
    check("A/5 فجوة بادئة اكتُشفت وجُلبت", int(c.get("gaps_detected") or 0) >= 1
          and int(c.get("fetched_new") or 0) > 38_000,
          f"detected={c.get('gaps_detected')} fetched_new={c.get('fetched_new')}")
    check("A/6 الشموع المسلَّمة للمحرك كاملة", df30 is not None and 43_100 <= len(df30) <= 43_210,
          f"rows={0 if df30 is None else len(df30)}")
    check("A/7 بطاقة الشفافية كاملة", all(
        c.get(k) is not None for k in
        ("requested_start", "requested_end", "stored_start", "stored_end",
         "expected_candles", "delivered_candles", "coverage_pct")
    ))
    return m2


async def test_d(session_maker, sm, cfg98: dict, ref: dict):
    banner("اختبار القبول D · إعادة حمولة #10000098 على مخزونها المتضرر (بلا حذف)")
    from datetime import datetime, timedelta, timezone as _tz

    from app.services.candle_cache import (
        CandleCacheService, _capture_df_schema, _records_from_df,
    )

    start = cfg98["start_date"]
    end = cfg98["end_date"]
    s_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    e_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

    # 1) جلب شظيتين حقيقيتين من Binance (خارج كاش القاعدة) — إعادة بناء
    #    مخزون #10000098 المصاب: شظية قديمة قبل النافذة + ذيل قرب نهايتها
    ds, _ = await make_services(session_maker)
    frag_old = await ds.get_historical_last_version(
        symbol="BTCUSDT", timeframe="1m", market="crypto",
        start_date=s_dt - timedelta(days=2), end_date=s_dt,
        use_cache=False,
    )
    frag_tail = await ds.get_historical_last_version(
        symbol="BTCUSDT", timeframe="1m", market="crypto",
        start_date=e_dt - timedelta(days=2), end_date=e_dt,
        use_cache=False,
    )
    schema = _capture_df_schema(frag_old)
    recs = _records_from_df(frag_old) + _records_from_df(frag_tail)
    dmg = CandleCacheService(session_maker=session_maker)
    await dmg._save(
        session_maker, "d:crypto:BTCUSDT:1m", "d", "BTCUSDT", "1m", "crypto",
        recs, schema, "seed damage — replica of #10000098 inventory",
    )
    print(f"  [المخزون المتضرر] {len(recs)} شمعة "
          f"(شظية قديمة {len(frag_old)} + ذيل {len(frag_tail)}) — مثل #10000098 تماماً")

    # 2) تشغيل حمولة #10000098 نفسها عبر المحرك الكامل دون حذف الكاش
    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig

    _, cached = await make_services(session_maker)
    engine = BacktestEngine(cached)
    config = BacktestConfig(**cfg98)
    result = await engine.run_backtest(config)
    m = dict(cached.last_meta or {})
    c = m.get("cache") or {}
    print(f"  [تشغيل المحرك] {card_line(m)}")
    print(f"  note: {c.get('note')}")
    print(f"  النتيجة: صفقات={result.total_trades} · PnL={result.total_pnl_percent:.4f}%"
          f" · رأس المال {result.initial_capital:.0f}→{result.final_capital:.2f}")
    print(f"  المرجع #10000099: صفقات={ref['trades']} · PnL={ref['pnl']:.4f}%")

    check("D/1 المحرك استلم نافذته كاملة ≈43,200",
          43_100 <= int(c.get("delivered_candles") or 0) <= 43_210,
          f"delivered={c.get('delivered_candles')}")
    check("D/2 coverage_pct == 100.0", c.get("coverage_pct") == 100.0,
          f"coverage={c.get('coverage_pct')}")
    check("D/3 gap_filled == true", c.get("gap_filled") is True)
    check("D/4 الفجوة اكتُشفت في المخزون المصاب",
          int(c.get("gaps_detected") or 0) >= 1, f"detected={c.get('gaps_detected')}")
    check("D/5 نفس عدد صفقات المرجع (#10000099)",
          result.total_trades == ref["trades"],
          f"got={result.total_trades} ref={ref['trades']}")
    check("D/6 نفس ربحية المرجع (±0.25%)",
          abs(float(result.total_pnl_percent) - ref["pnl"]) <= 0.25,
          f"got={result.total_pnl_percent:.4f} ref={ref['pnl']:.4f}")


async def test_c(session_maker, sm):
    banner("اختبار القبول C · SOLUSDT 1m · 477d: بارد ثم دافئ (لا تفشّط)")
    now = int(_time.time())
    _, cached = await make_services(session_maker)

    t0 = _time.perf_counter()
    df1 = await range_fetch_via_cache(cached, "SOLUSDT", "1m", "crypto", now - 477 * 86400, now)
    m1 = dict(cached.last_meta or {})
    c1 = m1.get("cache") or {}
    dt1 = _time.perf_counter() - t0
    print(f"  [بارد {dt1:.1f}s] {card_line(m1)}")
    print(f"  note: {c1.get('note')}")

    t0 = _time.perf_counter()
    df2 = await range_fetch_via_cache(cached, "SOLUSDT", "1m", "crypto", now - 477 * 86400, now)
    m2 = dict(cached.last_meta or {})
    c2 = m2.get("cache") or {}
    dt2 = _time.perf_counter() - t0
    print(f"  [دافئ {dt2:.1f}s] {card_line(m2)}")
    print(f"  note: {c2.get('note')}")

    expected = 477 * 1440
    d1 = int(c1.get("delivered_candles") or 0)
    d2 = int(c2.get("delivered_candles") or 0)
    check("C/1 الجلب البارد كامل (~686,880+)", d1 >= expected - 3_000,
          f"delivered={d1} expected={expected}")
    check("C/2 تغطية البارد 100%", c1.get("coverage_pct") == 100.0,
          f"coverage={c1.get('coverage_pct')} natural={c1.get('natural_gaps')}")
    check("C/3 الطلب الدافئ لا يفشّط (نفس التسليم ±2)",
          abs(d2 - d1) <= 2, f"warm={d2} cold={d1}")
    check("C/4 تغطية الدافئ 100%", c2.get("coverage_pct") == 100.0,
          f"coverage={c2.get('coverage_pct')}")
    check("C/5 الدافئ أسرع من البارد (كاش القرص+القاعدة)", dt2 < dt1,
          f"warm={dt2:.1f}s cold={dt1:.1f}s")
    check("C/6 لا فجوات متبقية في المسارين",
          c1.get("gap_filled") is True and c2.get("gap_filled") is True,
          f"cold_filled={c1.get('gap_filled')} warm_filled={c2.get('gap_filled')}")


async def test_b(session_maker, sm):
    banner("اختبار القبول B · SOLUSDT: مفتاح بأسابيع فقط ثم طلب 365d·1m")
    from app.services.candle_cache import CandleCacheService

    now = int(_time.time())
    svc = CandleCacheService(session_maker=session_maker)
    deleted = await svc.delete_entry("d:crypto:SOLUSDT:1m")
    print(f"  [تحضير] حذف مفتاح SOLUSDT: {deleted}")

    _, cached = await make_services(session_maker)
    # 1) ثلاثة أسابيع فقط
    await range_fetch_via_cache(cached, "SOLUSDT", "1m", "crypto", now - 21 * 86400, now)
    m1 = dict(cached.last_meta or {})
    print(f"  [تعبئة 21d] {card_line(m1)}")
    check("B/1 المخزون الآن أسابيع فقط (~30,240)",
          29_500 <= int((m1.get("cache") or {}).get("delivered_candles") or 0) <= 30_500,
          f"stored={(m1.get('cache') or {}).get('delivered_candles')}")

    # 2) طلب 365d — سيناريو #10000085 كان يعطي 5,717 (1.09%)
    df = await range_fetch_via_cache(cached, "SOLUSDT", "1m", "crypto", now - 365 * 86400, now)
    m2 = dict(cached.last_meta or {})
    c = m2.get("cache") or {}
    print(f"  [طلب 365d] {card_line(m2)}")
    print(f"  note: {c.get('note')}")
    check("B/2 جلب الفجوة البادئة ≈ 525,600",
          524_500 <= int(c.get("delivered_candles") or 0) <= 525_700,
          f"delivered={c.get('delivered_candles')}")
    check("B/3 coverage_pct == 100.0", c.get("coverage_pct") == 100.0,
          f"coverage={c.get('coverage_pct')}")
    check("B/4 gap_filled == true", c.get("gap_filled") is True)
    check("B/5 لا تكرار لسيناريو #10000085 (كان 5,717 = 1.09%)",
          int(c.get("delivered_candles") or 0) > 500_000,
          f"delivered={c.get('delivered_candles')}")
    check("B/6 الشموع المسلَّمة كاملة", df is not None and len(df) > 524_000,
          f"rows={0 if df is None else len(df)}")


async def main() -> None:
    from app.database.session import build_isolated_session_maker
    from app.services.task_registry import ensure_registry_tables

    sm, iso_engine = build_isolated_session_maker()
    try:
        await ensure_registry_tables()

        # حمولة #10000098 الحقيقية من سيرفر المستخدم + مرجع #10000099
        cfg98 = json.load(open("/tmp/cfg98.json"))
        ref = {"trades": 9, "pnl": -2.062622905599001}

        await test_a(sm, sm)
        await test_d(sm, sm, cfg98, ref)
        await test_c(sm, sm)
        await test_b(sm, sm)
    finally:
        await iso_engine.dispose()

    print("\n" + "═" * 72)
    print(f"النتيجة النهائية: {len(PASS)} نجاح / {len(FAIL)} فشل "
          f"· الزمن الكلي {_time.perf_counter() - T0:.0f}s")
    if FAIL:
        print("فشل:", FAIL)
        sys.exit(1)
    print("✅ R61 — كل اختبارات القبول الحقيقية ناجحة (Binance حي)")


if __name__ == "__main__":
    asyncio.run(main())
