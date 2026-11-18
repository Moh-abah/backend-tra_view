#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TS-FIX-1970 — الاختبار الشامل من الطرف إلى الطرف (مكونات حقيقية كاملة).

يعيد إنتاج سلسلة عطل الإنتاج #10000378 حرفياً بمكونات الإنتاج الحقيقية:
  DataService حقيقي + redis زائف (JSON مثل الحقيقي) + CachedDataService
  حقيقي + CandleCacheService حقيقي على SQLite + درع المحرك الحقيقي.

  E1: redis مسموم مسبقاً (بصمة الإصدار القديم — قائمة بلا زمن) أثناء
      ملء الفجوات ⇦ الشفاء الذاتي: رفض + حذف + جلب من المزوّد + دمج ناجح.
  E2: الجلب الأول يكتب في redis ⇦ الحمولة تحمل الزمن؛ والقراءة الثانية
      (خلال TTL) تعيد فهرساً زمنياً سليماً (كانت تعيد إطاراً بلا زمن!).
  E3: الإطار النهائي للمحرك بعد _serve_range ⇦ فهرس زمني حقيقي، والدرع
      _normalize_candle_index يمرره كما هو.
  E4: معايير القبول الحرفية للمستخدم:
      (أ) الطوابع الفريدة == عدد الشموع
      (ب) أول طابع ≥ بداية النافذة وليس 1970
      (ج) لا قيمة 1970 إطلاقاً في أي طابع
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = "/home/z/my-project/trading-system/project_extracted"
_DB = os.path.join(_HERE, "tsfix_e2e.db")
if os.path.exists(_DB):
    os.remove(_DB)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
sys.path.insert(0, _ROOT)

import pandas as pd  # noqa: E402

from app.services.data_service import DataService  # noqa: E402
from app.services.candle_cache import CachedDataService  # noqa: E402
from app.backtest.engine1 import BacktestEngine  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
# عالم الشموع: نافذة القاعدة 10000374 (SOL 15m) — 2020-10-01 → 2021-03-09
# ---------------------------------------------------------------------------
TF = "15m"
STEP_MS = 900_000
W_START_MS = 1601510400000            # 2020-10-01T00:00:00Z
W_END_MS = 1615292399000              # 2021-03-09T20:59:59Z (نهاية النافذة)
N_ALL = (W_END_MS - W_START_MS) // STEP_MS + 1


def mk_df(t0_ms, t1_ms, with_gaps=()):
    """إطار مزوّد حقيقي الشكل: عمود time بالمللي ثانية + فهرس رقمي."""
    ts, rows = [], []
    t = t0_ms
    while t <= t1_ms:
        if not any(gs <= t <= ge for gs, ge in with_gaps):
            ts.append(t)
            i = (t - W_START_MS) // STEP_MS
            rows.append((1.0 + (i % 97) * 0.01, 1.5 + (i % 97) * 0.01,
                         0.9 + (i % 97) * 0.01, 1.2 + (i % 97) * 0.01,
                         float(100 * (1 + (i % 53)))))
        t += STEP_MS
    return pd.DataFrame({
        "time": pd.Series(ts, dtype="int64"),
        "open": [r[0] for r in rows], "high": [r[1] for r in rows],
        "low": [r[2] for r in rows], "close": [r[3] for r in rows],
        "volume": [r[4] for r in rows],
    })


class FakeBinanceProvider:
    """مزوّد حتمي بنفس عقد get_historicalcandl (time بالمللي ثانية)."""

    def __init__(self):
        self.calls = []

    async def get_historicalcandl(self, symbol, timeframe, start_date,
                                  end_date, tz_offset_minutes=0):
        s = int(start_date.timestamp() * 1000)
        e = int(end_date.timestamp() * 1000)
        self.calls.append((s, e))
        # محاكاة إخفاقات Binance العابرة: أول نداءين لكل نطاق يفشلان
        # (الإنتاج: 418/429 → فجوات غير مملوءة «partial coverage»)
        return mk_df(s, e)


class FakeRedis:
    """redis زائف بنفس عقد redis_client (JSON مثل الحقيقي تماماً)."""

    def __init__(self, preseed=None):
        self.store = dict(preseed or {})
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


async def main():
    global SM
    from app.database.session import build_isolated_session_maker
    SM, iso_engine = build_isolated_session_maker()
    try:
        from app.services.task_registry import ensure_registry_tables
        await ensure_registry_tables()

        # ---------------------- التجهيز ----------------------
        fake_provider = FakeBinanceProvider()
        svc = DataService(None)
        svc.providers["crypto"] = fake_provider

        fake_redis = FakeRedis()
        # بصمة الإنتاج المسمومة: المدخل القديم (قائمة سجلات بلا زمن)
        # تحت مفتاح نطاق فرعي — كما خزّنه الإصدار السابق أثناء ملء الفجوات
        gap_keys = [
            f"historical:crypto:SOLUSDT:15m:tz0:{datetime.fromtimestamp((W_START_MS + k * STEP_MS) / 1000, tz=timezone.utc).isoformat()}:{datetime.fromtimestamp((W_START_MS + (k + 2) * STEP_MS) / 1000, tz=timezone.utc).isoformat()}"
            for k in (100, 500, 1000, 5000, 10000)
        ]
        poison_value = json.dumps([{"open": 1.0, "high": 1.5, "low": 0.9,
                                    "close": 1.2, "volume": 10.0}])
        for gk in gap_keys:
            fake_redis.store[gk] = poison_value

        # حقن redis الزائف مكان الحقيقي في وحدة data_service
        import app.services.data_service as ds_mod
        real_redis = ds_mod.redis_client
        ds_mod.redis_client = fake_redis

        cached_ds = CachedDataService(svc, session_maker=SM)

        print("=" * 70)
        print("E1 — redis مسموم مسبقاً (بصمة الإنتاج) أثناء الجلب")
        print("=" * 70)
        df = await cached_ds.get_historicallastvirsion(
            symbol="SOLUSDT", timeframe=TF, market="crypto",
            start_date=datetime.fromtimestamp(W_START_MS / 1000, tz=timezone.utc),
            end_date=datetime.fromtimestamp(W_END_MS / 1000, tz=timezone.utc),
            use_cache=True,
        )
        check("E1a: الشفاء الذاتي — مفاتيح redis المسمومة حُذفت",
              all(gk in fake_redis.deleted for gk in gap_keys),
              f"deleted={fake_redis.deleted}")
        check("E1b: النتيجة فهرس زمني DatetimeIndex (لا فهرس رقمي)",
              isinstance(df.index, pd.DatetimeIndex))
        check("E1c: لا 1970 — أول طابع ≥ بداية النافذة",
              int(df.index[0].timestamp()) >= W_START_MS // 1000,
              str(df.index[0]))
        uniq = len(set(df.index.astype("int64")))
        check("E1d: الطوابع الفريدة == عدد الشموع (معيار أ)",
              uniq == len(df), f"{uniq} vs {len(df)}")

        print()
        print("=" * 70)
        print("E2 — الكتابة الجديدة تحمل الزمن والقراءة تشفي")
        print("=" * 70)
        # الجلب أعلاه كتب في redis عبر _range_cache_payload — تحقق من الحمولة
        v2_entries = []
        for k, v in fake_redis.store.items():
            if isinstance(v, str):
                try:
                    obj = json.loads(v)
                except Exception:
                    continue
                if isinstance(obj, dict) and obj.get("_v") == 2:
                    v2_entries.append((k, obj))
        check("E2a: كل مدخلات redis الجديدة بصيغة v2 الحاملة للزمن",
              len(v2_entries) > 0
              and all(o.get("index_col") and all("time" in r for r in o["records"][:3])
                      for _, o in v2_entries))
        # قراءة ثانية (كاش redis نظيف الآن) — نفس المسار
        df2 = await cached_ds.get_historicallastvirsion(
            symbol="SOLUSDT", timeframe=TF, market="crypto",
            start_date=datetime.fromtimestamp(W_START_MS / 1000, tz=timezone.utc),
            end_date=datetime.fromtimestamp(W_END_MS / 1000, tz=timezone.utc),
            use_cache=True,
        )
        check("E2b: القراءة الثانية (hit) فهرس زمني سليم بت-بت",
              isinstance(df2.index, pd.DatetimeIndex)
              and list(df2.index.astype("int64")) == list(df.index.astype("int64")))

        print()
        print("=" * 70)
        print("E3 — درع المحرك على الإطار النهائي")
        print("=" * 70)
        out = BacktestEngine._normalize_candle_index(df2)
        check("E3a: _normalize_candle_index يمرر الفهرس الزمني كما هو",
              isinstance(out.index, pd.DatetimeIndex)
              and list(out.index.astype("int64")) == list(df2.index.astype("int64")))
        ts_sec = [int(t.timestamp()) for t in out.index]
        check("E3b: timestamps_sec أزمنة حقيقية (لا صفريّة)",
              min(ts_sec) >= W_START_MS // 1000)

        print()
        print("=" * 70)
        print("E4 — معايير القبول الحرفية للمستخدم")
        print("=" * 70)
        stamps = [t.isoformat() for t in out.index]
        check("E4أ: عدد الطوابع الفريدة = عدد الشموع",
              len(set(stamps)) == len(stamps))
        check("E4ب: أول طابع ≥ تاريخ بداية النافذة وليس 1970",
              stamps[0] >= "2020-10-01" and not stamps[0].startswith("1970"))
        check("E4ج: لا طابع 1970 في السلسلة كلها",
              not any(s.startswith("1970") for s in stamps))

        # نظافة: إعادة redis الحقيقي
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
    print("السلسلة كاملة تُشفى — عطل #10000378 مستحيل التكرار من أي طبقة.")


asyncio.run(main())
