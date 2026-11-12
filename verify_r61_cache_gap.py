# verify_r61_cache_gap.py
"""✅ R61 — اختبارات وحدة إصلاح فجوة كاش الشموع (مزوّد مصطنع حتمي).

يشغّل CandleCacheService._cached_window مباشرة على SQLite محلية بعالمِ
شموع اصطناعي 1m كامل السيطرة (لا شبكة) — فيثبّت سلوك الإصلاح بت-بت:

  T1  إعادة إنتاج عيب #10000098 (جبن سويسري: شظية قديمة قبل النافذة +
      ذيل قرب نهايتها وفراغ 26 يوماً بينهما) ⇦ كان يُسلَّم 13% بصمت،
      الآن: كشف + جلب الفجوة + دمج ⇦ 43,200 كاملة.
  T2  اختبار القبول A: كاش يومين فقط ثم طلب 30d ⇦ فجوة بادئة تُجلب
      بدقة وتُدمج ⇦ coverage 100 و gap_filled=true.
  T3  فجوة طبيعية: المصدر نفسه لا يملك ساعة كاملة ⇦ تُعلَن natural_gaps=1
      ولا تُحسب نقصاً (لا إعادة جلب أبدية ولا نجاح كاذب).
  T4  فشل جلب الفجوة (المزوّد يرمي استثناء) ⇦ ممنوع النجاح الصامت:
      coverage<100 و gaps_remaining=1 وملاحظة ⚠️.
  T5  تغطية كاملة نظيفة ⇦ صفر نداءات جلب، hit=true، 100.0.
  T6  R57 محفوظ: لا شمعة تُسلَّم بعد نهاية النافذة المطلوبة.
  T7  فجوة ذيلية ⇦ نفس سلوك «تحديث الرأس» R58 لكن بتحقق اكتمال.
  T8  بطاقة as_meta تحمل كل حقول الشفافية المطلوبة.
  T9  أكثر من 6 فجوات ⇦ دمجها في جلب واحد موحّد (حد نداءات المزوّد).
  T10 نافذة لا شموع فيها إطلاقاً من المخزون ⇦ النافذة كلها فجوة بادئة.

التشغيل:  python3 verify_r61_cache_gap.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# بيئة معزولة قبل أي استيراد للتطبيق
_HERE = os.path.dirname(os.path.abspath(__file__))
_DB = os.path.join(_HERE, "r61_unit_test.db")
if os.path.exists(_DB):
    os.remove(_DB)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ.setdefault("CANDLE_CACHE_GAP_TOLERANCE_MULT", "3")
sys.path.insert(0, _HERE)

from app.services.candle_cache import (  # noqa: E402
    CandleCacheService,
    _analyze_window_coverage,
    _natural_tolerance_s,
    _plan_gap_fetches,
)

MIN = 60
HOUR = 3600
DAY = 86400
TF = "1m"
INTERVAL = MIN
TOL = _natural_tolerance_s(INTERVAL, "crypto")
assert TOL == 3 * MIN, f"tolerance expected 180s, got {TOL}"

# نافذة 30d·1m — أرقام اختبار القبول A نفسها (بداية موائمة لشبكة الدقيقة
# حتى يكون العدّ حتمياً: الشمعة الاحتياطية قبل البداية +1 دائماً)
W_START = (1_700_000_000 // MIN) * MIN
W_END = W_START + 30 * DAY
EXPECTED = (W_END - W_START) // INTERVAL   # 43,200

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    mark = "✅" if cond else "❌"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))


def mk_candle(t: int, price: float = 100.0) -> dict:
    return {
        "time": t, "open": price, "high": price + 0.5,
        "low": price - 0.5, "close": price, "volume": 1.0,
    }


class FakeProvider:
    """مزوّد حتمي: عالم شموع كامل مع مناطق محجوبة وسياسة أخطاء."""

    def __init__(self, missing_ranges=(), fail_ranges=()):
        self.missing = [tuple(r) for r in missing_ranges]   # المصدر لا يملكها
        self.fail = [tuple(r) for r in fail_ranges]         # رمي استثناء
        self.calls: list[tuple[int, int]] = []

    def universe(self, t0: int, t1: int) -> list[dict]:
        out = []
        t = t0 - (t0 % INTERVAL)
        while t <= t1:
            if not any(ms <= t < me for ms, me in self.missing):
                out.append(mk_candle(t))
            t += INTERVAL
        return out

    async def fetch_range(self, s: int, e: int) -> list[dict]:
        self.calls.append((s, e))
        if any(fs <= s <= fe or fs <= e <= fe for fs, fe in self.fail):
            raise RuntimeError("simulated provider failure (throttle)")
        return self.universe(s, e)


async def seed(svc_sm, key_symbol: str, candles: list[dict]) -> None:
    """بذر المخزون مباشرة عبر حفظ الخدمة (نفس مسار الإنتاج)."""
    svc = CandleCacheService(session_maker=svc_sm)
    await svc._save(
        svc_sm, f"c:crypto:{key_symbol}:{TF}", "c", key_symbol, TF,
        "crypto", candles, None, "seed (unit test)",
    )


async def run_case(name: str, symbol: str, provider: FakeProvider):
    svc = CandleCacheService(session_maker=SM)
    res = await svc._cached_window(
        namespace="c", symbol=symbol, timeframe=TF, market="crypto",
        days=0, window_start=W_START, window_end=W_END,
        fetch_range=provider.fetch_range,
    )
    meta = res.as_meta()["cache"]
    print(f"\n━━ {name}")
    print(
        f"  hit={meta['hit']} delivered={meta['delivered_candles']}"
        f"/{meta['expected_candles']} coverage={meta['coverage_pct']}%"
        f" gaps={meta['gaps_detected']}→{meta['gaps_remaining']}"
        f" natural={meta['natural_gaps']} fills={meta['fill_calls']}"
        f" fetched_new={meta['fetched_new']}"
    )
    print(f"  note: {meta['note']}")
    return res, meta


async def main() -> None:
    global SM
    from app.database.session import build_isolated_session_maker

    SM, iso_engine = build_isolated_session_maker()
    try:
        from app.services.task_registry import ensure_registry_tables

        await ensure_registry_tables()

        # ───────────────── T1: إعادة إنتاج عيب #10000098 والإصلاح ───────
        # مخزون الإنتاج المصاب: شظية قديمة قبل بداية النافذة (يومان) + ذيل
        # قرب نهايتها (يومان) وفراغ 26 يوماً بينهما. R58 كان يقول hit:true
        # ويسلّم ~5,760 من 43,200 (13%) — نفس مرض #10000098 بالضبط.
        # ملاحظة دلالة hit: أول شمعة داخل النافذة عند R58 كانت "first_time
        # قديم" فقط — لا شمعة فعلياً تغطي بداية النافذة، فالصادق الآن
        # hit=false (الجلب هو المصدر الأساسي) والكاش يشارك بالدمج فقط.
        old_frag = [mk_candle(t) for t in range(W_START - 2 * DAY, W_START, MIN)]
        tail_frag = [mk_candle(t) for t in range(W_END - 2 * DAY, W_END, MIN)]
        await seed(SM, "SWISS", old_frag + tail_frag)
        prov = FakeProvider()
        res, meta = await run_case(
            "T1 · جبن سويسري #10000098 ⇦ كشف + جلب الفجوة + دمج", "SWISS", prov
        )
        check("T1 hit=false صادقة (لا شيء يغطي بداية النافذة)", meta["hit"] is False)
        check("T1 فجوات مكتشفة", meta["gaps_detected"] >= 1,
              f"detected={meta['gaps_detected']}")
        check("T1 الفجوة جُلبت ودمجت", meta["fill_calls"] >= 1)
        check("T1 التغطية 100%", meta["coverage_pct"] == 100.0)
        check("T1 التسليم كامل ≈43,200",
              abs(meta["delivered_candles"] - EXPECTED) <= 2,
              f"delivered={meta['delivered_candles']}")
        check("T1 gap_filled=true", meta["gap_filled"] is True)
        check("T1 المخزون شُفي (لا عودة للجبن)",
              abs(len(res.candles) - EXPECTED) <= 2,
              f"stored_now={len(res.candles)}")

        # ───────────────── T2: اختبار القبول A — يومان ثم 30d ─────────────
        two_d = [mk_candle(t) for t in range(W_END - 2 * DAY, W_END, MIN)]
        await seed(SM, "TWOD", two_d)
        prov = FakeProvider()
        res, meta = await run_case(
            "T2 · القبول A: كاش يومين ⇦ طلب 30d (فجوة بادئة)", "TWOD", prov
        )
        check("T2 فجوة بادئة ⇦ hit=false (الجلب هو المصدر)", meta["hit"] is False)
        check("T2 جلب واحد دقيق للفجوة", len(prov.calls) == 1,
              f"calls={prov.calls}")
        lead = prov.calls[0] if prov.calls else (0, 0)
        check("T2 الجلب يستهدف الفجوة البادئة (~28 يوماً)",
              abs((lead[1] - lead[0]) - 28 * DAY) < HOUR,
              f"span={(lead[1]-lead[0])/DAY:.2f}d")
        check("T2 التسليم ≈43,200", abs(meta["delivered_candles"] - EXPECTED) <= 2,
              f"delivered={meta['delivered_candles']}")
        check("T2 coverage=100.0", meta["coverage_pct"] == 100.0)
        check("T2 gap_filled=true", meta["gap_filled"] is True)

        # ───────────────── T3: فجوة طبيعية (المصدر فارغ أصلاً) ────────────
        nat_hole = (W_START + 10 * DAY, W_START + 10 * DAY + HOUR)
        prov = FakeProvider(missing_ranges=[nat_hole])
        res, meta = await run_case(
            "T3 · ساعة يفتقدها المصدر نفسه ⇦ natural_gaps", "NATU", prov
        )
        check("T3 لا تُحسب نقصاً (gap_filled=true)", meta["gap_filled"] is True)
        check("T3 natural_gaps=1", meta["natural_gaps"] == 1)
        check("T3 coverage=100.0 (طبيعية مستثناة)", meta["coverage_pct"] == 100.0)
        check("T3 gaps_remaining=0", meta["gaps_remaining"] == 0)
        check("T3 أُعيد محاولة ملئها مرة واحدة فقط",
              sum(1 for s, e in prov.calls if e - s <= 2 * HOUR) == 1)

        # ───────────────── T4: فشل الجلب ⇦ لا نجاح صامت ───────────────────
        await seed(SM, "SWISS", old_frag + tail_frag)  # نفس جبن T1
        prov = FakeProvider(fail_ranges=[(W_START, W_END)])
        res, meta = await run_case(
            "T4 · فشل جلب الفجوة ⇦ إعلان صريح (⚠️)", "SWISS", prov
        )
        check("T4 hit=false (فشل جلب الفجوة البادئة)", meta["hit"] is False)
        check("T4 gaps_remaining=1", meta["gaps_remaining"] == 1,
              f"remaining={meta['gaps_remaining']}")
        check("T4 gap_filled=false", meta["gap_filled"] is False)
        check("T4 coverage<100 معلَنة", (meta["coverage_pct"] or 0) < 20.0,
              f"coverage={meta['coverage_pct']}%")
        check("T4 الملاحظة تحمل ⚠️", "⚠️" in (meta["note"] or ""))
        check("T4 التسليم ما هو متاح فقط (~5,760)",
              meta["delivered_candles"] < 6_000,
              f"delivered={meta['delivered_candles']}")

        # ───────────────── T5: تغطية كاملة نظيفة ──────────────────────────
        full = prov.universe(W_START - HOUR, W_END - INTERVAL)
        await seed(SM, "FULL", full)
        prov = FakeProvider()
        res, meta = await run_case(
            "T5 · كاش مكتمل ⇦ صفر نداءات جلب", "FULL", prov
        )
        check("T5 hit=true", meta["hit"] is True)
        check("T5 صفر نداءات مزوّد", len(prov.calls) == 0, f"calls={prov.calls}")
        check("T5 fetched_new=0", meta["fetched_new"] == 0)
        check("T5 coverage=100.0", meta["coverage_pct"] == 100.0)
        check("T5 التسليم ≈43,200 (+شمعة إحماء R58)",
              abs(meta["delivered_candles"] - EXPECTED) <= 2,
              f"delivered={meta['delivered_candles']}")

        # ───────────────── T6: R57 — قصّ النهاية محفوظ ────────────────────
        beyond = prov.universe(W_START - HOUR, W_END + 3 * DAY)
        await seed(SM, "BEYOND", beyond)
        prov6 = FakeProvider()
        res, meta = await run_case(
            "T6 · مخزون يتجاوز النهاية ⇦ لا تسريب للذيل (R57)", "BEYOND", prov6
        )
        last_t = max(c["time"] for c in res.candles)
        check("T6 آخر شمعة ≤ النهاية − عرض الفريم",
              last_t <= W_END - INTERVAL, f"last={last_t} limit={W_END-INTERVAL}")
        check("T6 لا فجوة ذيلية زائفة (الذيل المخزون يغطي)",
              meta["gaps_remaining"] == 0 and meta["fill_calls"] == 0)

        # ───────────────── T7: فجوة ذيلية = تحديث رأس R58 ─────────────────
        stale = prov.universe(W_START - HOUR, W_END - 3 * HOUR)
        await seed(SM, "STALE", stale)
        prov = FakeProvider()
        res, meta = await run_case(
            "T7 · ذيل ناقص 3 ساعات ⇦ جلب رأس محقّق", "STALE", prov
        )
        check("T7 hit=true مع جلب الرأس", meta["hit"] is True)
        check("T7 جلب واحد [آخر شمعة ← النهاية]",
              len(prov.calls) == 1 and prov.calls[0][0] >= W_END - 3 * HOUR - MIN,
              f"calls={prov.calls}")
        check("T7 التسليم ≈43,200 (+شمعة إحماء R58)",
              abs(meta["delivered_candles"] - EXPECTED) <= 2,
              f"delivered={meta['delivered_candles']}")
        check("T7 coverage=100.0", meta["coverage_pct"] == 100.0)

        # ───────────────── T8: بطاقة الشفافية كاملة الحقول ────────────────
        need_keys = {
            "hit", "cached", "fetched_new", "total", "note",
            "requested_start", "requested_end", "stored_start", "stored_end",
            "expected_candles", "delivered_candles", "coverage_pct",
            "gap_filled", "gaps_detected", "gaps_remaining",
            "natural_gaps", "fill_calls", "fetch_incomplete",
        }
        check("T8 كل حقول البطاقة موجودة", need_keys.issubset(set(meta.keys())),
              f"missing={need_keys - set(meta.keys())}")
        check("T8 expected_candles=43,200", meta["expected_candles"] == EXPECTED)
        check("T8 التواريخ ISO", str(meta["requested_start"]).startswith("20"),
              str(meta["requested_start"]))

        # ───────────────── T9: >6 فجوات ⇦ جلب موحّد واحد ───────────────────
        swiss9 = []
        for day in range(30):
            seg_start = W_START + day * DAY
            # لكل يوم: شمعة واحدة فقط ثم فراغ اليوم كله (جبن متفشٍ)
            swiss9.append(mk_candle(seg_start))
        swiss9.append(mk_candle(W_END - INTERVAL))
        await seed(SM, "SWISS9", swiss9)
        prov = FakeProvider()
        res, meta = await run_case(
            "T9 · 29 فجوة ⇦ دمجها في جلب واحد موحّد", "SWISS9", prov
        )
        check("T9 فجوات كثيرة مكتشفة", meta["gaps_detected"] > 6,
              f"detected={meta['gaps_detected']}")
        check("T9 نداء جلب واحد موحّد", len(prov.calls) == 1,
              f"calls={len(prov.calls)}")
        check("T9 hit=true (أول شمعة عند البداية — لا فجوة بادئة)",
              meta["hit"] is True)
        check("T9 شُفي بالكامل",
              abs(meta["delivered_candles"] - EXPECTED) <= 2
              and meta["coverage_pct"] == 100.0,
              f"delivered={meta['delivered_candles']}")

        # ───────────────── T10: لا شموع داخل النافذة إطلاقاً ─────────────
        far_old = [mk_candle(t) for t in range(W_START - 30 * DAY, W_START - 29 * DAY, MIN)]
        await seed(SM, "FAROLD", far_old)
        prov = FakeProvider()
        res, meta = await run_case(
            "T10 · مخزون خارج النافذة كلياً ⇦ النافذة فجوة بادئة", "FAROLD", prov
        )
        check("T10 hit=false", meta["hit"] is False)
        check("T10 جلب النافذة المطلوبة بدقة",
              len(prov.calls) == 1 and prov.calls[0] == (W_START, W_END),
              f"calls={prov.calls}")
        check("T10 التسليم ≈43,200", meta["delivered_candles"] == EXPECTED)

        # ───────────────── تحليل نقي: محاذاة الشبكة ──────────────────────
        card = _analyze_window_coverage(
            [W_START + INTERVAL, W_START + 2 * INTERVAL],
            W_START + 30,  # بداية غير موائمة (فرق 30 ثانية فقط)
            W_START + 3 * INTERVAL,
            INTERVAL, TOL,
        )
        check("U1 بداية غير موائمة بثوانٍ ⇦ لا فجوة بادئة زائفة",
              card["holes"] == [] and card["leading_hole"] is False,
              f"holes={card['holes']}")
        card2 = _analyze_window_coverage(
            list(range(W_START, W_START + 10 * MIN, MIN)),
            W_START, W_START + HOUR, INTERVAL, TOL,
        )
        check("U2 فراغ 50 دقيقة ⇦ فجوة ذيلية مكتشفة",
              len(card2["holes"]) == 1 and card2["holes"][0][0] == W_START + 10 * MIN,
              f"holes={card2['holes']}")
        plan = _plan_gap_fetches([(i, i + 10) for i in range(20)])
        check("U3 خطة الدمج لـ20 فجوة ⇦ نطاق واحد", len(plan) == 1
              and plan[0] == (0, 29), f"plan={plan}")

        # ───────────────── وضع الأيام (المسار الحي get_historical) ────────
        # T11: كاش مكتمل برأس قديم ⇦ تحديث رأس R58 محفوظ بلا ترقية
        import time as _t
        now_real = int(_t.time())
        # محاذاة شبكة الدقيقة (الكون الاصطناعي يستخدم الأرضية الدقيقة)
        d_start = ((now_real - 30 * DAY) // MIN) * MIN
        now_g = (now_real // MIN) * MIN
        full_stale = [mk_candle(t) for t in range(d_start, now_real - 3 * HOUR, MIN)]
        await seed(SM, "DSTALE", full_stale)
        prov = FakeProvider()

        async def fetch_days(days: int):
            prov.calls.append((0, days))
            return prov.universe(((now_real - days * DAY) // MIN) * MIN, now_g)

        svc = CandleCacheService(session_maker=SM)
        res = await svc._cached_window(
            namespace="c", symbol="DSTALE", timeframe=TF, market="crypto",
            days=30, fetch_records=fetch_days,
        )
        meta = res.as_meta()["cache"]
        print(f"\n━━ T11 · أيام: رأس قديم 3 ساعات ⇦ تحديث رأس R58")
        print(f"  hit={meta['hit']} delivered={meta['delivered_candles']} "
              f"coverage={meta['coverage_pct']}% note={meta['note']}")
        check("T11 hit=true (كاش + رأس)", meta["hit"] is True)
        check("T11 تحديث رأس واحد فقط", len(prov.calls) == 1,
              f"calls={prov.calls}")
        check("T11 النافذة اكتملت بعد الرأس", meta["gap_filled"] is True
              and meta["coverage_pct"] == 100.0)

        # T12: فجوة وسطى في وضع الأيام ⇦ ترقية إلى جلب كامل شافٍ
        cheesy = [mk_candle(t) for t in range(d_start, ((now_real - 2 * DAY) // MIN) * MIN, MIN)]
        cheesy += [mk_candle(t) for t in range(((now_real - DAY) // MIN) * MIN, now_g, MIN)]
        await seed(SM, "DCHEESE", cheesy)
        prov = FakeProvider()
        svc = CandleCacheService(session_maker=SM)
        res = await svc._cached_window(
            namespace="c", symbol="DCHEESE", timeframe=TF, market="crypto",
            days=30, fetch_records=fetch_days,
        )
        meta = res.as_meta()["cache"]
        print(f"\n━━ T12 · أيام: فجوة وسطى ⇦ جلب كامل شافٍ")
        print(f"  hit={meta['hit']} delivered={meta['delivered_candles']} "
              f"coverage={meta['coverage_pct']}% note={meta['note']}")
        check("T12 الترقية لجلب كامل (hit=false)", meta["hit"] is False)
        check("T12 النافذة اكتملت", meta["gap_filled"] is True
              and meta["coverage_pct"] == 100.0)
        check("T12 المخزون شُفي (لا عودة للجبن)",
              abs(len(res.candles) - (30 * DAY // MIN)) <= 5,
              f"delivered={len(res.candles)}")

        # T13: فجوة بادئة في وضع الأيام ⇦ سلوك R58 (جلب كامل + دمج)
        recent_only = [mk_candle(t) for t in range(((now_real - 5 * DAY) // MIN) * MIN, now_g, MIN)]
        await seed(SM, "DRECENT", recent_only)
        prov = FakeProvider()
        svc = CandleCacheService(session_maker=SM)
        res = await svc._cached_window(
            namespace="c", symbol="DRECENT", timeframe=TF, market="crypto",
            days=30, fetch_records=fetch_days,
        )
        meta = res.as_meta()["cache"]
        print(f"\n━━ T13 · أيام: مخزون أحدث من النافذة ⇦ جلب كامل R58")
        print(f"  hit={meta['hit']} delivered={meta['delivered_candles']} "
              f"coverage={meta['coverage_pct']}% note={meta['note']}")
        check("T13 hit=false وجلب كامل", meta["hit"] is False
              and len(prov.calls) == 1)
        check("T13 النافذة اكتملت", meta["gap_filled"] is True
              and meta["coverage_pct"] == 100.0)

    finally:
        await iso_engine.dispose()

    print("\n" + "═" * 64)
    print(f"النتيجة: {len(PASS)} نجاح / {len(FAIL)} فشل")
    if FAIL:
        print("فشل:", FAIL)
        sys.exit(1)
    print("✅ R61 — كل اختبارات وحدة إصلاح فجوة الكاش ناجحة")


if __name__ == "__main__":
    asyncio.run(main())
