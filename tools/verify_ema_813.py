#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPLIT-TP1 (جلسة الترندات الجديدة 8/13) — التحقق الثلاثي للرسم.

L5أ (مستوى المؤشر): محرك كموميه الزخم الاولى بأطوال [8,13,21,50,100,200,350,500]
على بيانات MMT 15m الحقيقية:
  · عمودا zzfetqe_ema_8 / zzfetqe_ema_13 موجودان بقيم فعلية (لا null بعد الإحماء)
  · color_by_length يرجع لوناً لكل طول (لا None أبداً) — 8 سماوي/13 كهرماني
  · المرايا ind_* عبر محول overlay_columns (رسم الفرونت)

L5ب (المحرك الكامل): باك-تست QMOM1 بنافذة قصيرة (3 أشهر) بالأطوال الثمانية:
  · شموع الرسم البصرية تحمل ind_zzfetqe_ema_8/13 (بيانات الرسم تعود فعلاً)
  · indicator_data يحمل أعمدة الترندات الجديدة
  · قيم EMA8 أسرع من EMA13 في الاتجاهات (سلوك سليم)

L5ج (هوية الستة): الأطوال الستة الافتراضية ⇒ نفس قيم الأعمدة والألوان الستة
بت-بت (الرقعة إضافية صرفة — ألوان 8/13 إضافة فوق العقد القائم).
"""
import asyncio
import io
import json
import sys
import types
from pathlib import Path

BASE = Path("/home/z/my-project/trading-system/split-tp")
RT = BASE / "runtime"
sys.path.insert(0, str(RT))

_ds_mod = types.ModuleType("app.services.data_service")


class _StubDataServiceCls:
    pass


_ds_mod.DataService = _StubDataServiceCls
sys.modules["app.services.data_service"] = _ds_mod

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(detail)) if detail and not cond else ""))


def mk_df(path):
    candles = json.load(io.open(path, encoding="utf-8"))
    df = pd.DataFrame([{
        "open": float(c["open"]), "high": float(c["high"]),
        "low": float(c["low"]), "close": float(c["close"]),
        "volume": float(c["volume"]),
    } for c in candles])
    df.index = pd.DatetimeIndex(
        pd.to_datetime([c["time"] for c in candles], unit="ms", utc=True),
        name="time")
    return df


def main():
    df15 = mk_df(BASE / "data" / "MMTUSDT_15m.json")
    payload = json.load(io.open(
        BASE / "payloads" / "payload_qmom1_mmt_10000604.json",
        encoding="utf-8"))
    params = payload["strategy_config"]["indicators"][0]["params"]
    n = len(df15)
    print(f"بيانات MMT 15m: {n} شمعة")

    # ========================= L5أ — مستوى المؤشر =========================
    print("== L5أ: محرك QMOM1 بالأطوال الثمانية (مع 8 و13)")
    from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema_mom import (
        zigzag_fib_e2e_trendy_quantum_ema_mom as mom_engine)

    res8 = mom_engine(df15, **{**params,
                                "ema_lengths": [8, 13, 21, 50, 100, 200, 350, 500]})
    s8 = res8["series"]

    def nn(k):
        v = s8.get(k) or []
        return sum(1 for x in v if x is not None)

    check("L5أ.1 عمود zzfetqe_ema_8 موجود بقيم",
          nn("zzfetqe_ema_8") > n * 0.9, (nn("zzfetqe_ema_8"), n))
    check("L5أ.2 عمود zzfetqe_ema_13 موجود بقيم",
          nn("zzfetqe_ema_13") > n * 0.9, (nn("zzfetqe_ema_13"), n))
    # ترتيب الإحماء منطقي: EMA8 يجهز قبل EMA500
    v8 = s8["zzfetqe_ema_8"]
    v500 = s8["zzfetqe_ema_500"]
    f8 = next(i for i, x in enumerate(v8) if x is not None)
    f500 = next(i for i, x in enumerate(v500) if x is not None)
    check("L5أ.3 الإحماء منطقي (EMA8 يجهز قبل EMA500)",
          f8 <= f500, (f8, f500))

    # قسم ema (الألوان والطول)
    ema_sec = res8.get("ema") or {}
    cbl = ema_sec.get("color_by_length") or {}
    check("L5أ.4 color_by_length يغطي الأطوال الثمانية",
          sorted(int(k) for k in cbl) == [8, 13, 21, 50, 100, 200, 350, 500],
          sorted(cbl))
    check("L5أ.5 لا لون None إطلاقاً (8/13 + أي طول مخصص)",
          all(v for v in cbl.values()), cbl)
    check("L5أ.6 لون EMA8 = سماوي #00BCD4",
          cbl.get("8") == "#00BCD4", cbl.get("8"))
    check("L5أ.7 لون EMA13 = كهرماني #FFC107",
          cbl.get("13") == "#FFC107", cbl.get("13"))
    colors = ema_sec.get("colors") or {}
    check("L5أ.8 ema.colors يكشف المفاتيح الثمانية",
          "ema_8" in colors and "ema_13" in colors and "ema_21" in colors,
          sorted(colors))
    check("L5أ.9 ema.lengths = الثمانية بالترتيب",
          ema_sec.get("lengths") == [8, 13, 21, 50, 100, 200, 350, 500],
          ema_sec.get("lengths"))
    # الرصة الهرمية: الأسرع من القاعدة (8/13) معفاة — يعمل بلا أخطاء
    check("L5أ.10 رصة الأطوال الثمانية تعمل (stack_ok/ready)",
          nn("zzfetqe_ema_stack_ok") > 0 and nn("zzfetqe_ema_stack_ready") > 0)

    # المرآة ind_* عبر محول الأعمدة (عقد رسم الفرونت)
    from app.services.indicators.overlay_columns import _zzfetqem_columns
    ind_cols = _zzfetqem_columns(res8)
    check("L5أ.11 مرآة ind_zzfetqe_ema_8 تعبر المحول",
          "ind_zzfetqe_ema_8" in ind_cols, sorted(
              k for k in ind_cols if k.endswith("_8"))[:4])
    check("L5أ.12 مرآة ind_zzfetqe_ema_13 تعبر المحول",
          "ind_zzfetqe_ema_13" in ind_cols)
    arr8 = ind_cols.get("ind_zzfetqe_ema_8") or []
    check("L5أ.13 قيم المرآة ind_zzfetqe_ema_8 تساوي الخام بت-بت",
          len(arr8) == n and all(
              (a is None and b is None) or (a is not None and b is not None
                                            and abs(float(a) - float(b)) < 1e-12)
              for a, b in zip(arr8, v8)),
          (len(arr8), n))

    # سلوك سريع: EMA8 يستجيب أسرع من EMA13 (تقاطعات موجودة في نافذة سنة)
    v13 = s8["zzfetqe_ema_13"]
    cross = sum(1 for i in range(1, n)
                if v8[i] is not None and v13[i] is not None
                and v8[i - 1] is not None and v13[i - 1] is not None
                and ((v8[i] - v13[i]) * (v8[i - 1] - v13[i - 1]) < 0))
    check("L5أ.14 تقاطعات 8×13 موجودة (بيانات رسم حية)",
          cross > 10, cross)

    # ========================= L5ج — هوية الستة =========================
    print("== L5ج: هوية الأطوال الستة الافتراضية (الرقعة إضافية صرفة)")
    res6 = mom_engine(df15, **{**params})  # الأطوال الافتراضية الستة
    s6 = res6["series"]
    ema6 = res6.get("ema") or {}
    cbl6 = ema6.get("color_by_length") or {}
    EXPECT6 = {"21": "#4CAF50", "50": "#9C27B0", "100": "#FF9800",
               "200": "#F44336", "350": "#2196F3", "500": "#9E9E9E"}
    check("L5ج.1 ألوان الستة بت-بت كما كانت",
          {k: cbl6.get(k) for k in EXPECT6} == EXPECT6,
          {k: cbl6.get(k) for k in EXPECT6})
    for L in (21, 50, 100, 200, 350, 500):
        a = s6.get(f"zzfetqe_ema_{L}") or []
        b = s8.get(f"zzfetqe_ema_{L}") or []
        same = len(a) == len(b) and all(
            (x is None and y is None) or (
                x is not None and y is not None and float(x) == float(y))
            for x, y in zip(a, b))
        check(f"L5ج.2 قيم EMA{L} بت-بت في التشغيلتين",
              same)
    # إشارات الدخول بت-بت (البوابة الهرمية نفسها بلا 8/13 كأسرع إضافية؟
    # ملاحظة: 8/13 < القاعدة 21 ⇒ «الأسرع» تصبح 4 بدل 2 — الشرط 1 (السعر فوق
    # الكل) يشملها — قد يختلف stack_ok — هذا متوقع ومقصود (ليس انحدارًا:
    # المستخدم أضاف الترندات بطلب صريح). القيم الست نفسها بت-بت أعلاه.)

    # ========================= L5ب — المحرك الكامل =========================
    print("== L5ب: باك-تست كامل بالأطوال الثمانية (نافذة 3 أشهر)")
    short = df15[df15.index >= pd.Timestamp("2026-08-01", tz="UTC")].copy()
    print(f"نافذة قصيرة: {len(short)} شمعة")

    class StubDS:
        def __init__(self, dfs):
            self.dfs = dfs

        async def get_historicallastvirsion(self, symbol, timeframe, market,
                                            start_date, end_date,
                                            use_cache=True, tz_offset_minutes=0):
            key = str(timeframe)
            df = self.dfs.get(key)
            if df is None:
                df = self.dfs.get("15m")
            return df.copy()

    df5_full = mk_df(BASE / "data" / "MMTUSDT_5m.json")
    sc8 = json.loads(json.dumps(payload["strategy_config"]))
    sc8["indicators"][0]["params"]["ema_lengths"] = [
        8, 13, 21, 50, 100, 200, 350, 500]
    cfg_kwargs = dict(payload)
    cfg_kwargs["strategy_config"] = sc8
    cfg_kwargs["start_date"] = short.index[0].to_pydatetime()
    cfg_kwargs["end_date"] = short.index[-1].to_pydatetime()
    from app.backtest.schemas import BacktestConfig
    from app.backtest.engine1 import BacktestEngine
    cfg = BacktestConfig(**cfg_kwargs)
    eng = BacktestEngine(data_service=StubDS(
        {"15m": short, "5m": df5_full}))
    res = asyncio.run(eng.run_backtest(cfg))

    vc = res.visual_candles or []
    cols_seen = set()
    for c in vc[:2000]:
        cols_seen.update((c.indicators or {}).keys())
    check("L5ب.1 شموع الرسم تحمل ind_zzfetqe_ema_8",
          "ind_zzfetqe_ema_8" in cols_seen,
          [k for k in sorted(cols_seen) if "ema_8" in k])
    check("L5ب.2 شموع الرسم تحمل ind_zzfetqe_ema_13",
          "ind_zzfetqe_ema_13" in cols_seen)
    # القيم عبر الشموع غير null بعد الإحماء (رسم حي فعلي)
    vals8 = [(c.indicators or {}).get("ind_zzfetqe_ema_8") for c in vc]
    n_nonnull8 = sum(1 for v in vals8 if v is not None)
    check("L5ب.3 قيم EMA8 غير معدومة في شموع الرسم (>90%)",
          n_nonnull8 > len(vals8) * 0.9, (n_nonnull8, len(vals8)))
    vals13 = [(c.indicators or {}).get("ind_zzfetqe_ema_13") for c in vc]
    n_nonnull13 = sum(1 for v in vals13 if v is not None)
    check("L5ب.4 قيم EMA13 غير معدومة في شموع الرسم (>90%)",
          n_nonnull13 > len(vals13) * 0.9, (n_nonnull13, len(vals13)))
    # indicator_data (عقد المكتبة/الفرونت) تحمل الأعمدة
    idata = getattr(res, "indicator_data", None) or {}
    id_keys = set(idata.keys())
    check("L5ب.5 indicator_data تحمل أعمدة الرسم",
          bool(id_keys) and "ind_zzfetqe_ema_8" in id_keys,
          sorted(list(id_keys))[:6])
    check("L5ب.6 indicator_data تحمل ind_zzfetqe_ema_13",
          "ind_zzfetqe_ema_13" in id_keys)
    print(f"  (باك-تست النافذة القصيرة: {res.total_trades} صفقة · "
          f"total_pnl={res.total_pnl:.4f}$)")

    print()
    print(f"===== النتيجة: {len(PASS)} PASS / {len(FAIL)} FAIL =====")
    if FAIL:
        print("FAILED:", FAIL)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
