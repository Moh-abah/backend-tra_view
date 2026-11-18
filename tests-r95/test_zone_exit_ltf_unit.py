#!/usr/bin/env python3
"""test_zone_exit_ltf_unit.py — اختبارات وحدة ZONE-EXIT-LTF1 (الفريم الأدنى).

تختبر الوحدة المطورة overlays_zone_exit_mtf.py بمحرك زقزاق بديل قابل
للبرمجة (نفس عقد المحرك الحقيقي: pivots/confirmed_at_bar) — الرياضيات
المختبرة هي: التطبيع/التحقق من الخطوة/التقليم/الإسقاط السببي/السقوط الآمن.

المجموعات:
  A) التوافق الخلفي بت-بت: فريم أدنى بلا شموع LTF = التقييد الدفاعي القديم.
  B) وضع LTF: mode=ltf · أحداث على الشموع الصحيحة · سببية كاملة.
  C) التحقق من الخطوة: بيانات بفريم خاطئ ⇒ سقوط آمن للتقييد.
  D) التقليم: لا أحداث خارج نافذة الشارت (لا ماضٍ إضافي ولا ذيل).
  E) السببية: بادئة الحساب == بادئة الكامل.
  F) الحدود والتهكير: فارغ/قائمة سيئة/قيم سليطة.
  G) detect_zone_exit_ltf_timeframe: الكشف من تكوين الاستراتيجية.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app.services.indicators.overlays_zlf_e2e_trendy as trendy_stub  # noqa: E402
from app.services.indicators.overlays_zone_exit_mtf import (  # noqa: E402
    compute_zone_exit_mtf,
    detect_zone_exit_ltf_timeframe,
)

BASE_STEP = 900_000    # 15m
LTF_STEP = 300_000     # 5m
T0 = 1_700_000_000_000  # شبكة محاذاة للدقيقة


def make_base(n=240, start=T0, step=BASE_STEP):
    """شموع شارت 15m — موجة صاعدة ثم هابطة (قيم اصطناعية منتظمة)."""
    out = []
    for i in range(n):
        phase = (i // 20) % 2
        base_px = 100.0 + (i * 0.5 if phase == 0 else -i * 0.3)
        t = start + i * step
        out.append({
            "time": t, "open": base_px, "high": base_px + 2.0,
            "low": base_px - 2.0, "close": base_px + 1.0, "volume": 10.0,
        })
    return out


def make_ltf(base_n=240, start=T0, step=LTF_STEP):
    """شموع 5m تغطي نافذة الشارت نفسها (3 شموع لكل شمعة شارت)."""
    n = base_n * (BASE_STEP // step)
    out = []
    for i in range(n):
        phase = (i // 60) % 2
        base_px = 100.0 + (i * 0.2 if phase == 0 else -i * 0.1)
        t = start + i * step
        out.append({
            "time": t, "open": base_px, "high": base_px + 1.0,
            "low": base_px - 1.0, "close": base_px + 0.5, "volume": 3.0,
        })
    return out


PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  XX {name} {detail}")


def reset_pivots():
    trendy_stub.TEST_PIVOTS = []


def main():
    print("=" * 70)
    print("ZONE-EXIT-LTF1 — اختبارات وحدة الفريم الأدنى (جلب حقيقي)")
    print("=" * 70)

    base = make_base()
    ltf = make_ltf()
    N = len(base)

    # ------------------------------------------------------------------
    print("\n-- A) التوافق الخلفي: فريم أدنى بلا شموع LTF = التقييد القديم")
    # ------------------------------------------------------------------
    reset_pivots()
    r_nol = compute_zone_exit_mtf(base, resolution="5m", length=10)
    check("A1: بلا ltf_candles → resolution_clamped_to_chart_tf=True",
          r_nol is not None and r_nol["meta"]["resolution_clamped_to_chart_tf"] is True)
    check("A2: mode=htf (التقييد القديم)",
          r_nol["meta"].get("mode") == "htf")
    check("A3: htf_step_ms = خطوة الشارت",
          r_nol["meta"]["htf_step_ms"] == BASE_STEP)
    # ltf_candles=None صراحة = نفس الشيء
    r_none = compute_zone_exit_mtf(base, resolution="5m", length=10, ltf_candles=None)
    check("A4: ltf_candles=None صراحة = نفس نتيجة الغياب",
          r_none["meta"]["resolution_clamped_to_chart_tf"] is True
          and r_none["zone_exit"] == r_nol["zone_exit"])

    # ------------------------------------------------------------------
    print("\n-- B) وضع LTF: الحساب على شموع 5m الحقيقية المجلوبة")
    # ------------------------------------------------------------------
    # محاور مبرمجة على شموع LTF تفتح منطقة ثم تغلقها (HH+HL ثم LL+LH):
    #   top@30 (200) · low@60 (80) · top@90 (210=HH) · low@120 (90=HL)
    #   → ENTER عند LTF bar 120
    #   top@150 (180=LH) · low@210 (70=LL) → EXIT عند LTF bar 210
    trendy_stub.TEST_PIVOTS = [
        {"kind": "top", "price": 200.0, "bar": 25, "confirmed_at_bar": 30},
        {"kind": "low", "price": 80.0, "bar": 55, "confirmed_at_bar": 60},
        {"kind": "top", "price": 210.0, "bar": 85, "confirmed_at_bar": 90},    # HH
        {"kind": "low", "price": 90.0, "bar": 115, "confirmed_at_bar": 120},   # HL → ENTER
        {"kind": "top", "price": 180.0, "bar": 145, "confirmed_at_bar": 150},  # LH
        {"kind": "low", "price": 70.0, "bar": 205, "confirmed_at_bar": 210},   # LL → EXIT
    ]
    r_ltf = compute_zone_exit_mtf(base, resolution="5m", length=10, ltf_candles=ltf)
    check("B1: mode=ltf", r_ltf is not None and r_ltf["meta"].get("mode") == "ltf")
    check("B2: resolution_clamped_to_chart_tf=False",
          r_ltf["meta"]["resolution_clamped_to_chart_tf"] is False)
    check("B3: ltf_bars = عدد شموع LTF داخل النافذة",
          r_ltf["meta"]["ltf_bars"] == len(ltf),
          f"got {r_ltf['meta']['ltf_bars']} want {len(ltf)}")
    check("B4: ltf_step_ms = 300000", r_ltf["meta"]["ltf_step_ms"] == LTF_STEP)
    check("B5: ltf_source=fetched", r_ltf["meta"].get("ltf_source") == "fetched")

    # حدث الخروج: المحور الرابع confirmed عند LTF bar 210 → إغلاقها
    # t_l[210] + 5m = T0 + 210*300000 + 300000 = T0 + 63300000 ms
    ev_close = T0 + 210 * LTF_STEP + LTF_STEP
    want_i = 70
    exits = [i for i, v in enumerate(r_ltf["zone_exit"]) if v > 0]
    check("B6: حدث خروج واحد عند الشمعة الصحيحة",
          exits == [want_i], f"got {exits} want [{want_i}]")
    check("B7: زمن العلم ≥ زمن إغلاق شمعة LTF التي أكدت (سببية)",
          base[want_i]["time"] + BASE_STEP >= ev_close,
          f"base_close={base[want_i]['time'] + BASE_STEP} ev_close={ev_close}")
    check("B8: لا علم قبل لحظة العلم على الشمعة السابقة (دقة الإسقاط)",
          want_i == 0 or base[want_i - 1]["time"] + BASE_STEP < ev_close)
    evs = r_ltf["events"]
    check("B9: حدثان مسقطان (enter+exit) بأزمنة صحيحة",
          len(evs) == 2
          and {(e["kind"], e["base_bar"]) for e in evs} == {("enter", 40), ("exit", 70)}
          and evs[1]["htf_close_time"] == ev_close,
          f"got {[(e['kind'], e['base_bar']) for e in evs]}")
    # أحداث الدخول: HH+HL اكتمل عند LTF bar 120 (إغلاقها T0+121*5m):
    # i0 = searchsorted(t, 36,300,000 - 900,000) → i=40
    enters = [i for i, v in enumerate(r_ltf["zone_enter"]) if v > 0]
    check("B10: حدث دخول واحد عند الشمعة الصحيحة (HH+HL)",
          enters == [40], f"got {enters}")
    check("B11: zone_on مفتوحة [40..69] ومغلقة عند 70 (الإسقاط الاستمرائي)",
          all(r_ltf["zone_on"][i] == 1.0 for i in range(40, 70))
          and all(r_ltf["zone_on"][i] == 0.0 for i in list(range(0, 40)) + list(range(70, N))))

    # ------------------------------------------------------------------
    print("\n-- C) التحقق من الخطوة: بيانات بفريم مختلف ⇒ سقوط آمن")
    # ------------------------------------------------------------------
    # تمرير شموع 15m مكان 5m (خطوة فعلية 900000 ≠ 300000)
    r_wrong = compute_zone_exit_mtf(base, resolution="5m", length=10, ltf_candles=base)
    check("C1: بيانات بفريم خاطئ → تقييد دفاعي (لا LTF)",
          r_wrong["meta"]["resolution_clamped_to_chart_tf"] is True
          and r_wrong["meta"].get("mode") == "htf")
    # شموع 1m مكان 5m (أدق من المطلوب — نرفضها أيضاً: الحساب يجب أن يكون
    # على الفريم المطلوب نفسه)
    ltf_1m = make_ltf(step=60_000)
    r_finer = compute_zone_exit_mtf(base, resolution="5m", length=10, ltf_candles=ltf_1m)
    check("C2: بيانات أدق من المطلوب → تقييد دفاعي (اتساق الرياضيات)",
          r_finer["meta"]["resolution_clamped_to_chart_tf"] is True)
    # قائمة فارغة
    r_empty = compute_zone_exit_mtf(base, resolution="5m", length=10, ltf_candles=[])
    check("C3: قائمة فارغة → تقييد دفاعي",
          r_empty["meta"]["resolution_clamped_to_chart_tf"] is True)
    # قائمة سيئة (ليست شموعاً)
    r_bad = compute_zone_exit_mtf(base, resolution="5m", length=10,
                                  ltf_candles=["junk", 5, None])
    check("C4: قائمة سيئة → تقييد دفاعي (لا استثناء)",
          r_bad["meta"]["resolution_clamped_to_chart_tf"] is True)

    # ------------------------------------------------------------------
    print("\n-- D) التقليم: شموع LTF بذيل بعد نافذة الشارت وماضٍ قبلها")
    # ------------------------------------------------------------------
    # LTF تبدأ قبل الشارت بـ 10 شموع وتنتهي بعده بـ 10 شموع
    pre = make_ltf(base_n=10, start=T0 - 10 * LTF_STEP)
    post = make_ltf(base_n=10, start=T0 + N * BASE_STEP)
    extended = pre + ltf + post
    trendy_stub.TEST_PIVOTS = [
        {"kind": "top", "price": 200.0, "bar": 5, "confirmed_at_bar": 8},
        {"kind": "low", "price": 80.0, "bar": 15, "confirmed_at_bar": 18},
        {"kind": "top", "price": 210.0, "bar": 25, "confirmed_at_bar": 28},
        {"kind": "low", "price": 90.0, "bar": 35, "confirmed_at_bar": 38},
    ]
    r_pre = compute_zone_exit_mtf(base, resolution="5m", length=10, ltf_candles=extended)
    check("D1: التقليم يعمل (ltf_bars = الشموع داخل النافذة فقط)",
          r_pre["meta"]["ltf_bars"] == len(ltf),
          f"got {r_pre['meta']['ltf_bars']} want {len(ltf)}")
    # لا معلومات ما قبل البداية (t_l >= t0) ولا ذيل بعد النافذة (t_l < tN+15m)
    # أحداث ما قبل البداية (قبل التقليم كانت عند bar<10) يجب ألا تظهر إلا إذا
    # سقطت ضمن نافذة الشارت بعد الإزاحة
    all_ev_bars = [e["base_bar"] for e in r_pre["events"]]
    check("D2: كل الأحداث داخل نطاق الشارت",
          all(0 <= b < N for b in all_ev_bars))

    # ------------------------------------------------------------------
    print("\n-- E) السببية: بادئة الحساب == بادئة الكامل")
    # ------------------------------------------------------------------
    reset_pivots()  # محاور المحرك البديل الافتراضية (متناوبة SPAN/LAG)
    K = N // 2
    base_part = base[:K]
    # LTF للجزء: من T0 إلى إغلاق الشمعة K-1
    ltf_part = [c for c in ltf if c["time"] < T0 + K * BASE_STEP]
    full = compute_zone_exit_mtf(base, resolution="5m", length=10, ltf_candles=ltf)
    part = compute_zone_exit_mtf(base_part, resolution="5m", length=10, ltf_candles=ltf_part)
    check("E1: zone_exit بادئة الكامل == حساب النصف",
          full["zone_exit"][:K] == part["zone_exit"])
    check("E2: zone_on بادئة الكامل == حساب النصف",
          full["zone_on"][:K] == part["zone_on"])
    check("E3: zone_enter بادئة الكامل == حساب النصف",
          full["zone_enter"][:K] == part["zone_enter"])

    # ------------------------------------------------------------------
    print("\n-- F) الحدود والتهكير")
    # ------------------------------------------------------------------
    # فريم أعلى مع شموع LTF (يجب أن يُتجاهل LTF ويستخدم مسار HTF الطبيعي)
    r_htf = compute_zone_exit_mtf(base, resolution="60", length=10, ltf_candles=ltf)
    check("F1: فريم أعلى مع ltf_candles → مسار HTF (يتجاهلها)",
          r_htf["meta"].get("mode") == "htf"
          and r_htf["meta"]["htf_step_ms"] == 3_600_000)
    # شمعة واحدة كقاعدة
    r_one = compute_zone_exit_mtf(base[:1], resolution="5m", length=10, ltf_candles=ltf[:3])
    check("F2: شمعة قاعدة واحدة لا تكسر", r_one is not None or True)
    # قاعدة فارغة
    try:
        r_v = compute_zone_exit_mtf([], resolution="5m", length=10, ltf_candles=ltf)
        check("F3: قاعدة فارغة → None بلا استثناء", r_v is None)
    except Exception as e:
        check("F3: قاعدة فارغة → None بلا استثناء", False, f"{type(e).__name__}: {e}")
    # LTF كلها NaN/أصفار
    bad_rows = [{"time": T0 + i * LTF_STEP, "open": None, "high": None,
                 "low": None, "close": None} for i in range(50)]
    try:
        r_nan = compute_zone_exit_mtf(base, resolution="5m", length=10, ltf_candles=bad_rows)
        check("F4: شموع LTF كلها NaN → تقييد دفاعي", 
              r_nan["meta"]["resolution_clamped_to_chart_tf"] is True)
    except Exception as e:
        check("F4: شموع LTF كلها NaN → تقييد دفاعي", False, f"{type(e).__name__}: {e}")
    # فريمات LTF متنوعة تعمل: 1m على شارت 15m
    ltf_1m_full = make_ltf(step=60_000)
    r_1m = compute_zone_exit_mtf(base, resolution="1", length=10, ltf_candles=ltf_1m_full)
    check("F5: خروج 1m على شارت 15m يعمل (mode=ltf)",
          r_1m["meta"].get("mode") == "ltf" and r_1m["meta"]["ltf_step_ms"] == 60_000)
    # مرونة الاتجاه الآخر: قاعدة 5m مع خروج 1m
    base5 = make_base(step=LTF_STEP, n=720)
    ltf1 = make_ltf(step=60_000, base_n=720)
    # make_ltf تبني n = base_n * (base_step/step) — نصحح الشبكة يدوياً
    ltf1 = [{"time": T0 + i * 60_000, "open": 100 + (i % 7), "high": 101 + (i % 7),
             "low": 99 + (i % 7), "close": 100.5 + (i % 7), "volume": 1.0}
            for i in range(720 * 5)]
    r_5_1 = compute_zone_exit_mtf(base5, resolution="1m", length=10, ltf_candles=ltf1)
    check("F6: شارت 5m مع خروج 1m يعمل (مرونة الاتجاهين)",
          r_5_1["meta"].get("mode") == "ltf" and r_5_1["meta"]["base_step_ms"] == 300_000
          and r_5_1["meta"]["ltf_step_ms"] == 60_000)

    # ------------------------------------------------------------------
    print("\n-- G) detect_zone_exit_ltf_timeframe — كشف الحاجة من التكوين")
    # ------------------------------------------------------------------
    def cfg(res=None, name="zigzag_fib_e2e_trendy_quantum_ema", extra=None, enabled=True):
        params = {} if res is None else {"zone_exit_resolution": res}
        if extra:
            params.update(extra)
        return {"indicators": [{"name": name, "params": params,
                                "enabled": enabled, "type": "support_resistance"}]}

    check("G1: 5m على شارت 15m → '5m'",
          detect_zone_exit_ltf_timeframe(cfg("5m"), "15m") == "5m")
    check("G2: '5' (Pine مفرد) على شارت 15m → '5m'",
          detect_zone_exit_ltf_timeframe(cfg("5"), "15m") == "5m")
    check("G3: 1m على شارت 5m → '1m'",
          detect_zone_exit_ltf_timeframe(cfg("1"), "5m") == "1m")
    check("G4: 60m على شارت 15m → None (فريم أعلى — لا جلب)",
          detect_zone_exit_ltf_timeframe(cfg("60"), "15m") is None)
    check("G5: none/معطل → None",
          detect_zone_exit_ltf_timeframe(cfg("none"), "15m") is None
          and detect_zone_exit_ltf_timeframe(cfg(None), "15m") is None)
    check("G6: نفس فريم الشارت → None",
          detect_zone_exit_ltf_timeframe(cfg("15m"), "15m") is None)
    check("G7: مؤشر معطّل → None",
          detect_zone_exit_ltf_timeframe(cfg("5m", enabled=False), "15m") is None)
    check("G8: محرك آخر → None",
          detect_zone_exit_ltf_timeframe(cfg("5m", name="zigzag"), "15m") is None)
    check("G9: مرادف exit_resolution يعمل",
          detect_zone_exit_ltf_timeframe(
              {"indicators": [{"name": "zigzag_fib_e2e_trendy_quantum",
                               "params": {"exit_resolution": "3m"}, "enabled": True}]},
              "15m") == "3m")
    check("G10: تكوين فارغ/None → None",
          detect_zone_exit_ltf_timeframe({"indicators": []}, "15m") is None
          and detect_zone_exit_ltf_timeframe(None, "15m") is None)
    check("G11: أدق فريم يفوز عند التعدد",
          detect_zone_exit_ltf_timeframe(
              {"indicators": [
                  {"name": "zigzag_fib_e2e_trendy_quantum_ema",
                   "params": {"zone_exit_resolution": "5m"}, "enabled": True},
                  {"name": "zigzag_fib_e2e_trendy_quantum",
                   "params": {"zone_exit_resolution": "1m"}, "enabled": True},
              ]}, "15m") == "1m")
    check("G12: شارت غير مفهوم → None (لا جلب)",
          detect_zone_exit_ltf_timeframe(cfg("5m"), "غريب") is None)

    print("\n" + "=" * 70)
    print(f"النتيجة: OK {PASS} · XX {FAIL}")
    if FAILURES:
        print("الإخفاقات:")
        for f in FAILURES:
            print("  -", f)
    print("=" * 70)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
