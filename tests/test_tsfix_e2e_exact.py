#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TS-FIX-1970 — إعادة إنتاج سلسلة عطل الإنتاج #10000378 من الطرف إلى الطرف.

المكونات حقيقية بالكامل: DataService + CachedDataService + CandleCacheService
(SQLite) + درع engine1 — مع redis زائف بنفس عقد الحقيقي (JSON).

السيناريو الحرفي للإنتاج:
  * مخزون قاعدة البيانات (فضاء d) فيه نافذة كاملة مع 5 فجوات (حالة ما بعد
    #10000375) — cache hit مع «full coverage from cache» مبدئياً.
  * redis يحمل مدخلات مسمومة تحت مفاتيح نطاقات الفجوات الخمسة بالضبط
    (بصمة الإصدار القديم: قائمة سجلات بلا زمن).
  * المزوّد سليم (تعافى من التهدئة كما في #10000379).

قبل الإصلاح: جلب الفجوة يقرأ redis المسموم ⇦ إطار بلا زمن ⇦ مخطط مسموم
يُلتقط ⇦ إعادة البناء تطرد time ⇦ المحرك يحوّل الفهرس الرقمي 0..n إلى
نانو-ثوانٍ ⇦ 15,313 شمعة بطوابع 1970.

بعد الإصلاح: الشفاء الذاتي في كل طبقة.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = "/home/z/my-project/trading-system/project_extracted"
_DB = os.path.join(_HERE, "tsfix_e2e2.db")
if os.path.exists(_DB):
    os.remove(_DB)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
sys.path.insert(0, _ROOT)

import pandas as pd  # noqa: E402

from app.services.data_service import DataService  # noqa: E402
from app.services.candle_cache import (  # noqa: E402
    CandleCacheService,
    CachedDataService,
    _capture_df_schema,
    _records_from_df,
)
from app.backtest.engine1 import BacktestEngine  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
# نافذة القاعدة 10000374 (SOL 15m) — 2020-10-01 → 2021-03-09
# ---------------------------------------------------------------------------
TF = "15m"
STEP_MS = 900_000
W_START_MS = 1601510400000
W_END_MS = 1615292400000  # 2021-03-09T21:00:00Z (حد الشبكة)

# مواضع الفجوات الخمس (بأعداد الشموع من بداية النافذة) — كل فجوة 9 شموع
GAP_SPOTS = [100, 500, 1000, 5000, 10000]
GAP_LEN = 9


def price_at(i):
    return 1.0 + (i % 97) * 0.01


def _build(skip_gaps: bool):
    """إطار المزوّد — skip_gaps=True يبني نسخة المخزون (بفجوات 45 شمعة)."""
    ts, o, h, l, c, v = [], [], [], [], [], []
    i = 0
    t = W_START_MS
    while t < W_END_MS:
        if skip_gaps and any(s <= i < s + GAP_LEN for s in GAP_SPOTS):
            pass  # شمعة مفقودة من المخزون فقط — المزوّد يملكها
        else:
            p = price_at(i)
            ts.append(t)
            o.append(p); h.append(p + 0.5); l.append(p - 0.3)
            c.append(p + 0.2); v.append(float(100 * (1 + (i % 53))))
        t += STEP_MS
        i += 1
    return pd.DataFrame({"time": pd.Series(ts, dtype="int64"), "open": o,
                         "high": h, "low": l, "close": c, "volume": v})


UNIVERSE = _build(skip_gaps=False)       # عالم المزوّد: كامل بلا فجوات
STORED = _build(skip_gaps=True)          # مخزون القاعدة: مع الفجوات
GAP_BOUNDS_MS = []
for s in GAP_SPOTS:
    g0 = W_START_MS + s * STEP_MS          # أول شمعة مفقودة
    g1 = W_START_MS + (s + GAP_LEN - 1) * STEP_MS  # آخر شمعة مفقودة
    GAP_BOUNDS_MS.append((g0, g1))


class FakeBinanceProvider:
    """مزوّد حتمي بنفس عقد get_historicalcandl — سليم دوماً."""

    def __init__(self):
        self.calls = []

    async def get_historicalcandl(self, symbol, timeframe, start_date,
                                  end_date, tz_offset_minutes=0):
        s = int(start_date.timestamp() * 1000)
        e = int(end_date.timestamp() * 1000)
        self.calls.append((s, e))
        sub = UNIVERSE[(UNIVERSE["time"] >= s) & (UNIVERSE["time"] <= e)]
        return sub.reset_index(drop=True)


class FakeRedis:
    """redis زائف بنفس عقد redis_client — JSON مثل الحقيقي تماماً."""

    def __init__(self):
        self.store = {}
        self.deleted = []

    async def get_cached(self, key):
        v = self.store.get(key)
        return json.loads(v) if isinstance(v, str) else v

    async def set_cached(self, key, value, expire=300):
        self.store[key] = json.dumps(value)
        return True

    async def delete_cached(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)
        return True


def redis_key_for(s_sec, e_sec):
    a = datetime.fromtimestamp(int(s_sec), tz=timezone.utc).isoformat()
    b = datetime.fromtimestamp(int(e_sec), tz=timezone.utc).isoformat()
    return f"historical:crypto:SOLUSDT:15m:tz0:{a}:{b}"


async def main():
    from app.database.session import build_isolated_session_maker
    SM, iso_engine = build_isolated_session_maker()
    try:
        from app.services.task_registry import ensure_registry_tables
        await ensure_registry_tables()

        # ---------------- بذر مخزون القاعدة (فضاء d) ----------------
        # سجلات جيدة (بزمن ISO) + مخطط جيد — حالة ما بعد #10000375
        seeded = STORED.copy()
        seeded["time"] = pd.to_datetime(seeded["time"], unit="ms", utc=True)
        seeded = seeded.set_index("time")
        good_schema = _capture_df_schema(seeded)
        good_records = _records_from_df(seeded)
        cache_svc = CandleCacheService(session_maker=SM)
        await cache_svc._save(
            SM, "d:crypto:SOLUSDT:15m", "d", "SOLUSDT", TF, "crypto",
            good_records, good_schema, "seed (e2e)",
        )
        print(f"[seed] مخزون القاعدة: {len(good_records)} شمعة مع {len(GAP_SPOTS)} فجوات")

        # ---------------- تجهيز الخدمات ----------------
        fake_provider = FakeBinanceProvider()
        svc = DataService(None)
        svc.providers["crypto"] = fake_provider
        fake_redis = FakeRedis()

        # تسميم redis تحت مفاتيح نطاقات الفجوات الخمسة بالضبط:
        # فجوة بين آخر شمعة مغطاة T_prev وأول شمعة مغطاة بعدها T_next ⇦
        # الجلب يكون للنطاق (T_prev, T_next) بالثواني — نفس مفتاح الإنتاج.
        poison_keys = []
        for g0_ms, g1_ms in GAP_BOUNDS_MS:
            prev_ms = g0_ms - STEP_MS   # آخر شمعة مغطاة قبل الفجوة
            next_ms = g1_ms + STEP_MS   # أول شمعة مغطاة بعد الفجوة
            k = redis_key_for(prev_ms // 1000, next_ms // 1000)
            poison_keys.append(k)
            fake_redis.store[k] = json.dumps(
                [{"open": 1.0, "high": 1.5, "low": 0.9, "close": 1.2,
                  "volume": 10.0} for _ in range(GAP_LEN)]
            )
        print(f"[poison] {len(poison_keys)} مدخلات redis مسمومة (بصمة الإصدار القديم)")

        import app.services.data_service as ds_mod
        real_redis = ds_mod.redis_client
        ds_mod.redis_client = fake_redis

        cached_ds = CachedDataService(svc, session_maker=SM)

        # ---------------- التشغيل (نفس نداء engine1) ----------------
        print()
        print("=" * 70)
        print("التشغيل — نفس نداء engine1 على نافذة القاعدة")
        print("=" * 70)
        df = await cached_ds.get_historicallastvirsion(
            symbol="SOLUSDT", timeframe=TF, market="crypto",
            start_date=datetime.fromtimestamp(W_START_MS / 1000, tz=timezone.utc),
            end_date=datetime.fromtimestamp(W_END_MS / 1000, tz=timezone.utc),
            use_cache=True,
        )

        meta = cached_ds.last_meta.get("cache") or {}
        print(f"  cache.note: {meta.get('note')}")
        print(f"  delivered: {meta.get('delivered_candles')} | "
              f"coverage: {meta.get('coverage_pct')}% | "
              f"gaps_remaining: {meta.get('gaps_remaining')}")

        print()
        print("E1 — الشفاء الذاتي لمدخلات redis المسمومة")
        check("E1a: المدخلات المسمومة الخمسة حُذفت",
              all(k in fake_redis.deleted for k in poison_keys),
              f"deleted={len(fake_redis.deleted)}")
        check("E1b: الفجوات امتلأت فعلاً من المزوّد (بعد تجاوز السمّ)",
              meta.get("gaps_remaining") == 0
              and "gap fill" in str(meta.get("note")))

        print()
        print("E2 — الإطار المسلَّم للمحرك")
        check("E2a: فهرس زمني DatetimeIndex (لا فهرس رقمي 0..n)",
              isinstance(df.index, pd.DatetimeIndex))
        check("E2b: عدد الشموع = الكامل بعد ملء الفجوات",
              len(df) == (W_END_MS - W_START_MS) // STEP_MS,
              f"{len(df)}")
        check("E2c: الطوابع الفريدة == عدد الشموع (معيار أ)",
              len(set(df.index.astype("int64"))) == len(df))
        check("E2d: أول طابع ≥ بداية النافذة وليس 1970 (معيار ب)",
              int(df.index[0].timestamp()) >= W_START_MS // 1000
              and not str(df.index[0]).startswith("1970"),
              str(df.index[0]))
        check("E2e: لا طابع 1970 في السلسلة (معيار ج)",
              not any(str(t).startswith("1970") for t in df.index))
        # شموع الفجوة نفسها جلبت بأسعار المزوّد
        gap_i = GAP_SPOTS[0]
        gap_t = pd.Timestamp(W_START_MS + gap_i * STEP_MS, unit="ms", tz="UTC")
        check("E2f: شموع الفجوة موجودة فعلاً بعد الملء",
              gap_t in df.index)

        print()
        print("E3 — درع المحرك على الإطار النهائي")
        out = BacktestEngine._normalize_candle_index(df)
        check("E3a: الفهرس الزمني يمر كما هو بت-بت",
              isinstance(out.index, pd.DatetimeIndex)
              and list(out.index.astype("int64")) == list(df.index.astype("int64")))
        ts_sec = [int(t.timestamp()) for t in out.index]
        check("E3b: timestamps_sec للمحرك أزمنة حقيقية",
              min(ts_sec) >= W_START_MS // 1000)

        # نظافة
        ds_mod.redis_client = real_redis

    finally:
        await iso_engine.dispose()
        if os.path.exists(_DB):
            os.remove(_DB)

    print()
    print("=" * 70)
    print(f"الخلاصة: {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("الفاشلات:", FAIL)
        sys.exit(1)
    print("سلسلة #10000378 كاملة تُشفى — الطوابع 1970 مستحيلة التكرار.")


asyncio.run(main())
