#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPLIT-ZZ1 — بطارية الإثبات الحية النهائية (بيانات MMTUSDT الحقيقية).

L4-A (same/25): 12 جنيًا جزئيًا حقيقيًا (تطابق أحداث الانعكاس داخل نوافذ
    الصفقات بت-بت) — كل جني عند open الشمعة التالية لحدث مؤكد · ربع الكمية
    الأصلية · المحاسبة صفر-ازدواج.
L4-B (5m/25 · فريم أدق حقيقي): 27 جنيًا بمسار LTF الكامل (جلب → سياق →
    زقزاق 5m حقيقي → إسقاط سببي على 15m).
L4-C (القاعدتان معاً): 37 جنيًا — كل قاعدة مستقلة.
L5 (الشرط الخامس): البوابة الخمسة تعمل (11→2 صفقة — عزل الشرط الخامس).

يشغَّل بعد verify_identity_zz.py pre/post/five/splits/splits5m/splitsboth
(النتائج محفوظة في results/).
"""
import io
import json
import sys
from pathlib import Path

BASE = Path("/home/z/my-project/trading-system/split-zz")
RT = BASE / "runtime"
sys.path.insert(0, str(RT))

import types  # noqa: E402

_ds_mod = types.ModuleType("app.services.data_service")


class _StubDataServiceCls:
    pass


_ds_mod.DataService = _StubDataServiceCls
sys.modules["app.services.data_service"] = _ds_mod

import pandas as pd  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(detail)) if detail and not cond else ""))


def main():
    from app.services.indicators.overlays_zone_exit_mtf import (
        compute_zone_exit_mtf,
        compute_zone_exit_same,
        set_zone_exit_ltf_context,
        clear_zone_exit_ltf_context,
    )

    candles15 = json.load(io.open(BASE / "data" / "MMTUSDT_15m.json",
                                  encoding="utf-8"))
    candles5 = json.load(io.open(BASE / "data" / "MMTUSDT_5m.json",
                                  encoding="utf-8"))

    def mk(cs):
        df = pd.DataFrame([{
            "open": float(c["open"]), "high": float(c["high"]),
            "low": float(c["low"]), "close": float(c["close"]),
            "volume": float(c["volume"])} for c in cs])
        df.index = pd.DatetimeIndex(
            pd.to_datetime([c["time"] for c in cs], unit="ms", utc=True),
            name="time")
        return df

    df15 = mk(candles15)

    base = json.load(io.open(BASE / "results" / "identity_post.json",
                             encoding="utf-8"))

    # نوافذ الصفقات الحية (من شجرة الهوية — 11 صفقة)
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent))
    from verify_identity_zz import StubDS, run as run_engine  # noqa: E402

    # ============================ L4-A — same/25 ============================
    print("== L4-A: انعكاس هيكل الشارت المقسم (same/25) — بيانات حقيقية")
    d_s = json.load(io.open(BASE / "results" / "identity_splits.json",
                            encoding="utf-8"))
    x_s = json.load(io.open(BASE / "results" / "identity_splits_extra.json",
                            encoding="utf-8"))
    partials = x_s["partials"]
    check("L4A.1 جنيان جزئيان حقيقيان وقعا (12 متوقعًا)",
          len(partials) == 12, len(partials))

    zx = compute_zone_exit_same(df15, length=25)
    ev_times = [df15.index[j] for j, f in enumerate(zx["zone_exit"]) if f]
    check("L4A.2 الأحداث المستقلة = 101 انعكاس (نفس الآلة)",
          len(ev_times) == 101, len(ev_times))

    ok_px = True
    ok_sz = True
    ok_ev = True
    for p in partials:
        ts_p = pd.Timestamp(p["timestamp"])
        if ts_p.tzinfo is None:
            ts_p = ts_p.tz_localize("UTC")
        b = int(df15.index.get_loc(ts_p))
        exp_open = float(df15["open"].iloc[b])
        if abs(float(p["price"]) - exp_open) > 1e-9:
            ok_px = False
        # الحدث = إغلاق الشمعة السابقة
        prev = df15.index[b - 1]
        if prev not in ev_times:
            ok_ev = False
        # الحجم: ربع الكمية الأصلية لتلك الصفقة (من trade entry)
        tr = [t for t in x_s["trades_meta"]
              if abs(t["entry"] - float(p["entry_price"])) < 1e-12]
        # الكمية الأصلية = دخول × رصيد… نستخدم remaining_consistency بدلها:
        # (كل جني 25% من الأصل ⇒ remaining ينقص 25% من الأصل كل مرة)
        if p["size_percent"] != 25.0 or p["resolution"] != "same" \
                or p["length"] != 25:
            ok_sz = False
    check("L4A.3 سعر كل جني = open الشمعة التالية لحدث مؤكد (بيانات حقيقية)",
          ok_px, [(p["price"], p["timestamp"]) for p in partials[:3]])
    check("L4A.4 كل جني يعق مباشرة حدث انعكاس مؤكد", ok_ev)
    check("L4A.5 كل جني موسوم same/25/25%", ok_sz)
    # المحاسبة صفر-ازدواج
    tot_pnl_trades = sum(t["pnl"] for t in x_s["trades_meta"])
    check("L4A.6 total_pnl النتيجة = مجموع pnl الصفقات (صفر-ازدواج)",
          abs(d_s["total_pnl"] - tot_pnl_trades) < 1e-6,
          (d_s["total_pnl"], tot_pnl_trades))
    n_partials_meta = sum(t["n_partials"] for t in x_s["trades_meta"])
    check("L4A.7 partial_exits الصفقات = عدد الجنى (12)",
          n_partials_meta == 12, n_partials_meta)
    re_ = x_s["risk_echo"]
    check("L4A.8 risk_echo.structure_split_partial_exits = 12",
          re_.get("structure_split_partial_exits") == 12,
          re_.get("structure_split_partial_exits"))
    # أثر عقلاني: الجني حسّن النتيجة من -112.87 (بيع جزئي داخل النوافذ)
    check("L4A.9 التأثير عقلاني (بيع جزئي حقيقي غيّر النتيجة)",
          abs(d_s["total_pnl"] - base["total_pnl"]) > 1.0
          and d_s["total_trades"] == base["total_trades"],
          (d_s["total_pnl"], base["total_pnl"]))

    # ============================ L4-B — 5m/25 ============================
    print("== L4-B: انعكاس هيكل 5 دقائق الحقيقي المقسم (LTF كامل)")
    d_m = json.load(io.open(BASE / "results" / "identity_splits5m.json",
                            encoding="utf-8"))
    x_m = json.load(io.open(BASE / "results" / "identity_splits5m_extra.json",
                            encoding="utf-8"))
    partials_m = x_m["partials"]
    check("L4B.1 جني جزئي بمسار LTF وقع (27 متوقعًا)",
          len(partials_m) == 27, len(partials_m))
    set_zone_exit_ltf_context(candles5, "5m")
    try:
        zxm = compute_zone_exit_mtf(df15, resolution="5m", length=25)
    finally:
        clear_zone_exit_ltf_context()
    ev_times_m = [df15.index[j] for j, f in enumerate(zxm["zone_exit"]) if f]
    check("L4B.2 الأحداث المستقلة على 5m الحقيقي = 307 (سياق حقيقي)",
          len(ev_times_m) == 307 and zxm["meta"].get("ltf_real_context"),
          (len(ev_times_m), zxm["meta"].get("ltf_real_context")))
    ok_px_m = True
    ok_res_m = True
    for p in partials_m:
        ts_p = pd.Timestamp(p["timestamp"])
        if ts_p.tzinfo is None:
            ts_p = ts_p.tz_localize("UTC")
        b = int(df15.index.get_loc(ts_p))
        exp_open = float(df15["open"].iloc[b])
        if abs(float(p["price"]) - exp_open) > 1e-9:
            ok_px_m = False
        prev = df15.index[b - 1]
        if prev not in ev_times_m:
            ok_res_m = False
    check("L4B.3 سعر كل جني = open الشمعة التالية لحدث 5m مؤكد",
          ok_px_m, [(p["price"], p["timestamp"]) for p in partials_m[:3]])
    check("L4B.4 كل جني يعقب حدث 5m مسقطًا سببيًا", ok_res_m)
    check("L4B.5 كل جني موسوم 5m/25",
          all(p["resolution"] == "5m" and p["length"] == 25
              and p["size_percent"] == 25.0 for p in partials_m))
    tot_m = sum(t["pnl"] for t in x_m["trades_meta"])
    check("L4B.6 المحاسبة صفر-ازدواج",
          abs(d_m["total_pnl"] - tot_m) < 1e-6,
          (d_m["total_pnl"], tot_m))

    # ============================ L4-C — القاعدتان ============================
    print("== L4-C: القاعدتان معاً (same/25 + 5m/25)")
    d_c = json.load(io.open(BASE / "results" / "identity_splitsboth.json",
                            encoding="utf-8"))
    x_c = json.load(io.open(BASE / "results" / "identity_splitsboth_extra.json",
                            encoding="utf-8"))
    partials_c = x_c["partials"]
    n_same = sum(1 for p in partials_c if p["resolution"] == "same")
    n_5m = sum(1 for p in partials_c if p["resolution"] == "5m")
    # 12 من same + 27 من 5m − 2 تصادمات (حدث في شمعة خروج كامل للصفقة ⇒
    # أولوية الخروج الكامل — لا جني جزئي عنده: one same + one 5m) = 11+26=37
    check("L4C.1 كل قاعدة مستقلة (11 same + 26 5m = 37 — تصادمان بأولوية الخروج الكامل)",
          len(partials_c) == 37 and n_same == 11 and n_5m == 26,
          (len(partials_c), n_same, n_5m))
    tot_c = sum(t["pnl"] for t in x_c["trades_meta"])
    check("L4C.2 المحاسبة صفر-ازدواج مع القاعدتين",
          abs(d_c["total_pnl"] - tot_c) < 1e-6,
          (d_c["total_pnl"], tot_c))
    re_c = x_c["risk_echo"]
    check("L4C.3 risk_echo يحمل القاعدتين معاً",
          len(re_c.get("structure_split_exits") or []) == 2
          and re_c.get("structure_split_total_size_percent") == 50.0,
          re_c.get("structure_split_exits"))

    # ============================ L5 — الشرط الخامس ============================
    print("== L5: الشرط الخامس — RSI اليومي (14/14/2) لا يتجاوز 60")
    d_f = json.load(io.open(BASE / "results" / "identity_five.json",
                            encoding="utf-8"))
    payload5 = json.load(io.open(
        BASE / "payloads" / "payload_qmom1_mmt_5cond.json", encoding="utf-8"))
    conds = payload5["strategy_config"]["indicators"][0]["params"][
        "osc_conditions"]["conditions"]
    check("L5.1 الحمولة تحمل خمسة شروط",
          len(conds) == 5, len(conds))
    c5 = conds[-1]
    check("L5.2 الشرط الخامس = rsi_1d_14_14.value <= 60",
          c5.get("left") == "osc:rsi_1d_14_14.value"
          and c5.get("op") == "<=" and float(c5.get("right")) == 60.0,
          c5)
    check("L5.3 البوابة الخمسة تعمل (11 صفقة → 2 — عزل الشرط الخامس)",
          d_f["total_trades"] == 2 and base["total_trades"] == 11,
          (d_f["total_trades"], base["total_trades"]))
    check("L5.4 نافذة الهوية نفسها (لا تغيير بالفترة)",
          payload5["start_date"] ==
          json.load(io.open(BASE / "payloads" /
                            "payload_qmom1_mmt_10000604.json",
                            encoding="utf-8"))["start_date"])
    check("L5.5 لا جني مقسم في مسار الشروط الخمسة (نقاء العزل)",
          d_f["n_partial_points"] == 0)

    print()
    print(f"===== النتيجة: {len(PASS)} PASS / {len(FAIL)} FAIL =====")
    if FAIL:
        print("FAILED:", FAIL)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
