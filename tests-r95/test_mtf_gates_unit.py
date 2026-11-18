#!/usr/bin/env python3
"""test_mtf_gates_unit.py — اختبارات وحدة MTF-GATES1 ببيانات Binance حقيقية.

التحقق الذهبي: قيم MACD/RSI المسقطة من شموع 15m (بناء HTF + إسقاط سببي)
تُقارن بقيم مرجعية محسوبة مباشرة على شموع Binance الحقيقية للفريم الأعلى
(4h/1h/1d) — تطابق عائم كامل متوقع لأن التجميع والإسقاط يتبعان نفس حدود
الشموع الرسمية.
"""
import json
import math
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.indicators.overlays_mtf_gates import mtf_gates_engine  # noqa: E402

BASE_URL = "https://api.binance.com/api/v3/klines"
SYMBOL = "SOLUSDT"
CACHE = Path("/home/z/r95-work/mtg_test/cache")
CACHE.mkdir(parents=True, exist_ok=True)

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


def fetch(interval, start_ms, end_ms):
    key = CACHE / f"{SYMBOL}_{interval}_{start_ms}_{end_ms}.json"
    if key.exists():
        return json.loads(key.read_text())
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        url = f"{BASE_URL}?symbol={SYMBOL}&interval={interval}&startTime={cursor}&limit=1000"
        for attempt in range(5):
            try:
                r = subprocess.run(["curl", "-s", "--max-time", "30", url],
                                   capture_output=True, text=True, timeout=40)
                batch = json.loads(r.stdout)
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1 + attempt)
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        last_open = batch[-1][0]
        if len(batch) < 1000 or last_open >= end_ms:
            break
        cursor = last_open + 1
    # شموع مغلقة فقط (احذف الأخيرة إن لم تُغلق بعد)
    now_ms = int(time.time() * 1000)
    unit = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}[interval]
    rows = [r for r in rows if r[0] + unit <= now_ms]
    key.write_text(json.dumps(rows))
    return rows


def to_candles(rows):
    return [{"time": int(r[0]), "open": float(r[1]), "high": float(r[2]),
             "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
            for r in rows]


# ------------------------------ مرجع رياضي مستقل ------------------------------

def ref_ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    prev = sum(vals[:n]) / n
    out[n - 1] = prev
    a = 2.0 / (n + 1)
    for i in range(n, len(vals)):
        prev = vals[i] * a + prev * (1 - a)
        out[i] = prev
    return out


def ref_macd(closes, f, s, g):
    ef, es = ref_ema(closes, f), ref_ema(closes, s)
    line = [None if (ef[i] is None or es[i] is None) else ef[i] - es[i] for i in range(len(closes))]
    first = next((i for i, v in enumerate(line) if v is not None), None)
    sig = [None] * len(closes)
    if first is not None:
        sub = ref_ema([v for v in line[first:] if v is not None], g)
        for i, v in enumerate(sub):
            sig[first + i] = v
    return line, sig


def ref_rsi(closes, period):
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains[i] = max(ch, 0.0)
        losses[i] = max(-ch, 0.0)
    ag = sum(gains[1:period + 1]) / period
    al = sum(losses[1:period + 1]) / period
    def val(g, l):
        return 100.0 if l <= 0 and g > 0 else (50.0 if l <= 0 else 100.0 - 100.0 / (1.0 + g / l))
    out[period] = val(ag, al)
    for i in range(period + 1, len(closes)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        out[i] = val(ag, al)
    return out


def main():
    print("=" * 70)
    print("MTF-GATES1 — اختبارات بوابة MACD 4h + RSI متعدد الفريمات")
    print("=" * 70)

    end_ms = int(time.time() * 1000) // 900_000 * 900_000
    start_ms = end_ms - 90 * 86_400_000  # 90 يوماً

    base15 = to_candles(fetch("15m", start_ms, end_ms))
    real_1h = to_candles(fetch("1h", start_ms - 3_600_000, end_ms))
    real_4h = to_candles(fetch("4h", start_ms - 14_400_000, end_ms))
    real_1d = to_candles(fetch("1d", start_ms - 86_400_000, end_ms))
    N = len(base15)
    print(f"\n15m: {N} شمعة | 1h: {len(real_1h)} | 4h: {len(real_4h)} | 1d: {len(real_1d)}")

    res = mtf_gates_engine(
        base15,
        macd_timeframe="240", macd_fast=12, macd_slow=26, macd_signal=4,
        rsi_timeframes=["60", "240"], rsi_reference_timeframe="1D",
        rsi_period=14, rsi_ma_length=14, rsi_bb_std=2.0,
        source="close", warmup_neutral=True,
    )
    ser = res["series"]
    meta = res["mtf_gates"]
    check("M0: البوابة موجودة بطول الشموع", len(ser["mtg_gate"]) == N)
    check("M1: meta الماكد مفعّل بفريم 240",
          meta["macd"].get("enabled") and meta["macd"].get("resolution") == "240")
    check("M2: meta RSI مفعّلة بمرجع 1D",
          meta["rsi"].get("enabled") and meta["rsi"].get("reference") == "1D")

    # ------------------------------------------------------------- المرجع
    closes4 = [c["close"] for c in real_4h]
    line4, sig4 = ref_macd(closes4, 12, 26, 4)
    closes1 = [c["close"] for c in real_1h]
    rsi1 = ref_rsi(closes1, 14)
    rsi4 = ref_rsi(closes4, 14)
    closes1d = [c["close"] for c in real_1d]
    rsi1d = ref_rsi(closes1d, 14)

    def htf_at(real_candles, htf_close_times, i_base, base_step=900_000):
        """فهرس آخر شمعة HTF حقيقية مغلقة ≤ إغلاق شمعة القاعدة i."""
        cutoff = base15[i_base]["time"] + base_step
        j = -1
        for k, ct in enumerate(htf_close_times):
            if ct <= cutoff:
                j = k
            else:
                break
        return j

    t4 = [c["time"] + 14_400_000 for c in real_4h]
    t1 = [c["time"] + 3_600_000 for c in real_1h]
    t1d = [c["time"] + 86_400_000 for c in real_1d]

    # قارن على عينة موزعة (كل 37 شمعة)
    mism_line = mism_sig = mism_r1 = mism_r4 = mism_r1d = 0
    compared = 0
    gate_mism = 0
    for i in range(0, N, 37):
        j4 = htf_at(real_4h, t4, i)
        j1 = htf_at(real_1h, t1, i)
        j1d = htf_at(real_1d, t1d, i)
        if j4 < 0 or j1 < 0 or j1d < 0:
            continue
        compared += 1
        ml, ms = ser["mtg_macd_line"][i], ser["mtg_macd_signal"][i]
        if ml is None or line4[j4] is None:
            if not (ml is None and line4[j4] is None):
                mism_line += 1
        elif abs(ml - line4[j4]) > 1e-9:
            mism_line += 1
        if ms is None or sig4[j4] is None:
            if not (ms is None and sig4[j4] is None):
                mism_sig += 1
        elif abs(ms - sig4[j4]) > 1e-9:
            mism_sig += 1
        r1 = ser["mtg_rsi_60_value"][i]
        if r1 is None or rsi1[j1] is None:
            if not (r1 is None and rsi1[j1] is None):
                mism_r1 += 1
        elif abs(r1 - rsi1[j1]) > 1e-9:
            mism_r1 += 1
        r4 = ser["mtg_rsi_240_value"][i]
        if r4 is None or rsi4[j4] is None:
            if not (r4 is None and rsi4[j4] is None):
                mism_r4 += 1
        elif abs(r4 - rsi4[j4]) > 1e-9:
            mism_r4 += 1
        rd = ser["mtg_rsi_1D_value"][i]
        if rd is None or rsi1d[j1d] is None:
            if not (rd is None and rsi1d[j1d] is None):
                mism_r1d += 1
        elif abs(rd - rsi1d[j1d]) > 1e-9:
            mism_r1d += 1
        # البوابة نفسها (مع عقد حياد الإحماء R74: أي قيمة مفقودة ⇒ مفتوحة)
        vals_ready = (line4[j4] is not None and sig4[j4] is not None
                      and rsi1[j1] is not None and rsi4[j4] is not None
                      and rsi1d[j1d] is not None)
        if not vals_ready:
            want = True  # إحماء — حياد مفتوح
        else:
            want = (line4[j4] > 0 and line4[j4] > sig4[j4]
                    and rsi1[j1] > rsi1d[j1d] and rsi4[j4] > rsi1d[j1d])
        if (ser["mtg_gate"][i] > 0.5) != want:
            gate_mism += 1

    check(f"G1: MACD 4h line يطابق المرجع ({compared} نقطة)", mism_line == 0,
          f"mism={mism_line}")
    check(f"G2: MACD 4h signal يطابق المرجع", mism_sig == 0, f"mism={mism_sig}")
    check(f"G3: RSI 1h يطابق المرجع", mism_r1 == 0, f"mism={mism_r1}")
    check(f"G4: RSI 4h يطابق المرجع", mism_r4 == 0, f"mism={mism_r4}")
    check(f"G5: RSI 1D يطابق المرجع", mism_r1d == 0, f"mism={mism_r1d}")
    check(f"G6: البوابة نفسها تطابق المنطق المرجعي", gate_mism == 0,
          f"mism={gate_mism}")

    # ---------------------------------------------------- خصائص البوابة
    gate = ser["mtg_gate"]
    on = sum(1 for g in gate if g > 0.5)
    print(f"\nالبوابة مفتوحة {on}/{N} شمعة ({100.0 * on / N:.1f}%) · إحماء {meta['warmup_bars']}")
    check("P1: البوابة ليست كلها مفتوحة (تميّز حقيقي)", 0 < on < N)
    check("P2: البوابة ليست كلها مغلقة", on > 0)
    check("P3: الإحماء موجب ثم قيم", meta["warmup_bars"] > 0)
    check("P4: sub-gates موجودة", "mtg_macd_ok" in ser and "mtg_rsi_ok" in ser)
    mo = sum(1 for g in ser["mtg_macd_ok"] if g > 0.5)
    ro = sum(1 for g in ser["mtg_rsi_ok"] if g > 0.5)
    check("P5: macd_ok ⊇ gate و rsi_ok ⊇ gate (AND)",
          on <= mo and on <= ro, f"gate={on} macd={mo} rsi={ro}")

    # ------------------------------------------------------- السببية
    K = N // 2
    part = mtf_gates_engine(
        base15[:K],
        macd_timeframe="240", macd_fast=12, macd_slow=26, macd_signal=4,
        rsi_timeframes=["60", "240"], rsi_reference_timeframe="1D",
        rsi_period=14, rsi_ma_length=14, rsi_bb_std=2.0)
    check("C1: بادئة gate == بادئة الكامل (سببية)",
          part["series"]["mtg_gate"] == gate[:K])
    check("C2: بادئة macd_line == بادئة الكامل",
          part["series"]["mtg_macd_line"] == ser["mtg_macd_line"][:K])
    check("C3: بادئة rsi_1D == بادئة الكامل",
          part["series"]["mtg_rsi_1D_value"] == ser["mtg_rsi_1D_value"][:K])

    # ----------------------------------------------- التعطيل والحواف
    r_dis = mtf_gates_engine(base15, macd_timeframe="none",
                             rsi_reference_timeframe="none")
    check("D1: كل شيء معطل → هوية (gate=1)",
          all(g > 0.5 for g in r_dis["series"]["mtg_gate"]))
    r_macd_only = mtf_gates_engine(base15, macd_timeframe="240",
                                   rsi_reference_timeframe="none")
    check("D2: ماكد فقط يعمل",
          r_macd_only["series"]["mtg_macd_line"] == ser["mtg_macd_line"])
    r_rsi_only = mtf_gates_engine(base15, macd_timeframe="none",
                                  rsi_timeframes=["60", "240"],
                                  rsi_reference_timeframe="1D")
    check("D3: RSI فقط يعمل",
          r_rsi_only["series"]["mtg_rsi_60_value"] == ser["mtg_rsi_60_value"])
    # فريم مرجع مطابق لنسخة → استبعاد ذاتي
    r_self = mtf_gates_engine(base15, macd_timeframe="none",
                              rsi_timeframes=["1D", "60"],
                              rsi_reference_timeframe="1D")
    check("D4: المرجع ضمن النسخ يُستبعد (لا مقارنة ذات)",
          any("مطابق للمرجع" in w for w in r_self["mtf_gates"].get("warnings", [])))
    # مرادفات صيغ الفريم
    r_alias = mtf_gates_engine(base15, macd_timeframe="4h",
                               rsi_timeframes=["1h", "4h"],
                               rsi_reference_timeframe="1d")
    check("D5: مرادفات الصيغ (4h/1h/1d) نفس النتائج",
          r_alias["series"]["mtg_gate"] == gate)
    # warmup_neutral=false
    r_strict = mtf_gates_engine(base15, macd_timeframe="240",
                                rsi_timeframes=["60", "240"],
                                rsi_reference_timeframe="1D", warmup_neutral=False)
    strict_off = sum(1 for g in r_strict["series"]["mtg_gate"] if g > 0.5)
    check("D6: warmup_neutral=false يحجب الإحماء",
          strict_off <= on and r_strict["series"]["mtg_gate"][0] == 0.0)
    # بيانات فارغة
    r_empty = mtf_gates_engine([])
    check("D7: بيانات فارغة لا تكسر (هوية)", "mtg_gate" in r_empty["series"])
    # شموع قليلة (أقل من إحماء اليومي) — بوابة إحماء مفتوحة
    r_tiny = mtf_gates_engine(base15[:100], macd_timeframe="240",
                              rsi_timeframes=["60", "240"],
                              rsi_reference_timeframe="1D")
    check("D8: نافذة قصيرة = إحماء كامل (حياد R74)",
          all(g > 0.5 for g in r_tiny["series"]["mtg_gate"]))

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
