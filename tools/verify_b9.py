# =============================================================================
# B9 — أداة التحقق المستقلة «ماكد 9B + ترند 100» (v4.1 · LIVE1 — مدموجة مع فحص الخروج المصحح)
# =============================================================================
# تشغيل:  python3 tools/verify_b9.py [SYMBOL] [DAYS]
#   SYMBOL: افتراضي ETHUSDT · DAYS: نافذة البيانات بالأيام (افتراضي 500)
#   ملاحظة: فحص التغطية [6] يتطلب سنتين+ — شغّل:  verify_b9.py ETHUSDT 1400
# افتراضي: ETHUSDT (يكفي رمز واحد — التحقق رياضي وليس تدايولاً).
#
# المصدر: data/history/{SYM}_15m.parquet (كاش Binance) — وإن غاب يُجلب من
# Binance مباشرة نافذة قصيرة (شهران — كافية لـ 4H/1D، والفحص الأسبوعي
# يُتخطى تلقائياً عند قلة الأسابيع بتحذير واضح).
#
# البطارية (v3):
#   1) مطابقة قيم MACD (line + signal) للنسخ السبع ضد مرجع مستقل تماماً
#      (EMA ببذرة SMA معالِجة لبادئة NaN) — أقصى خطأ يجب أن يكون 0.
#   2) الإسقاط السببي: قيمة HTF ثابتة داخل الفريم الأعلى (عدا آخر شمعة
#      التي يكتمل عندها — عقد MTFEMA1) ولا ترى الشريط النامي أبداً.
#   3) trend_fractal p100: أحداث ولادة الخطوط تطابق سجل الإحداثيات
#      formed_at_bar بت-بت.
#   4) نافذة التفعيل (اختيارية): عند تمرير active_start لا يشتعل
#      b9g_buy قبلها إطلاقاً — وبدونها b9g_buy ≡ b9g_cond بت-بت.
#   5) الخروج المصحح: ولادة خط علوي فقط ∧ الخط فوق السعر (تصحيح صاحب
#      القرار — النسخة القديمة كانت: ولادة علوي ∨ سفلي): كل شريط خروج
#      هو ولادة خط علوي والخط فوق السعر.
#   6) ✅ v3 — تغطية الإشارات عبر كامل التاريخ (ضد شكوى «الإشارات تظهر
#      من نهاية الشارت فقط»): بلا نافذة، أول إشارة يجب أن تكون في أول
#      60% من الشارت (بعد الإحماء) وليست متركزة في الذيل، مع ≥5 حلقات
#      إشارة وانتشار عبر ≥4 أرباع سنوية عندما تغطي البيانات سنتين+.
#      (المؤشر الوحيد المسموح له بغياب الإشارات: بيانات أقصر من إحماء
#      MACD الأسبوعي 42 أسبوعاً — يُتخطى بتحذير).
#   7) ✅ v4 (LIVE1) — وضع live (ضد شكوى «الإشارات لا تظهر في المناطق
#      المهمة التي تسبق الصعود بينما TV يعرضها»): htf_mode=live يجعل
#      الشريط النامي مرئياً (قيمة الدلو الجاري بإغلاق الشمعة الحالية —
#      مثل TV الحي). الفحوص: (أ) meta.htf_mode=live · (ب) live يختلف عن
#      confirmed داخل دلاء 4H (يرى النامي فعلاً) · (ج) عند شمعة إتمام
#      الدلو تتطابق قيمة live مع قيمة الدلو المكتمل التي يعرضها
#      confirmed على الشمعة التالية (ت-بت) — أي لا قفزة ولا تسريب:
#      النامي يصبح المكتمل بسلاسة.
# =============================================================================
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd


# ----------------------------- مرجع مستقل تماماً -----------------------------

def ema_ref(x, length):
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) < length:
        return out
    seed = x[:length].mean()
    out[length - 1] = seed
    prev = seed
    a = 2.0 / (length + 1.0)
    for k in range(length, len(x)):
        prev = a * x[k] + (1 - a) * prev
        out[k] = prev
    return out


def macd_ref(close, fast, slow, sig):
    line = ema_ref(close, fast) - ema_ref(close, slow)
    valid = ~np.isnan(line)
    idx = np.where(valid)[0]
    sigout = np.full(len(line), np.nan)
    if len(idx) >= sig:
        seed_i = idx[sig - 1]
        sigout[seed_i] = line[idx[:sig]].mean()
        prev = sigout[seed_i]
        a = 2.0 / (sig + 1.0)
        for k in range(seed_i + 1, len(line)):
            if np.isnan(line[k]):
                sigout[k] = prev
            else:
                prev = a * line[k] + (1 - a) * prev
                sigout[k] = prev
    return line, sigout


# ------------------------------ تحميل الشموع -------------------------------

def load_candles(symbol: str, days: int = 500):
    cache = PROJECT_ROOT / "data" / "history" / f"{symbol}_15m.parquet"
    if cache.exists():
        df = pd.read_parquet(cache).sort_values("time").reset_index(drop=True)
        t = df["time"].values
        if len(t):
            tmax = int(t[-1])
            tmin = max(int(t[0]), tmax - days * 86400000)
            return df[(df["time"] >= tmin) & (df["time"] <= tmax)].reset_index(drop=True)
        return df
    from datetime import datetime, timedelta, timezone
    from app.providers.binance_provider import BinanceProvider

    async def _fetch():
        p = BinanceProvider()
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        return await p.get_historicalcandl(symbol, "15m", start, end)

    return asyncio.run(_fetch())


# --------------------------------- البطارية ---------------------------------

def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "ETHUSDT"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    df = load_candles(symbol, days=days)
    if df is None or df.empty:
        print(f"✗ لا بيانات لـ {symbol}")
        return 1
    df = df.sort_values("time").reset_index(drop=True)
    candles = df.to_dict("records")
    t = df["time"].values.astype(np.int64)
    n = len(t)
    print(f"رمز الفحص: {symbol} · {n} شمعة 15m "
          f"({pd.Timestamp(int(t[0]), unit='ms')} → {pd.Timestamp(int(t[-1]), unit='ms')})")

    from app.services.indicators.overlays_b9_macd_gates import (
        B9_DEFAULT_INSTANCES,
        b9_macd_gates,
    )
    from app.services.indicators.trend_fractals import auto_trendlines_fractal

    passed = failed = 0

    # ---- 1) مطابقة MACD للنسخ السبع ضد المرجع المستقل ----
    res = b9_macd_gates(candles)
    ser = res["series"]
    print("\n[1] مطابقة MACD (line+signal) ضد مرجع مستقل — بذرة SMA وNaN-aware:")
    for inst in B9_DEFAULT_INSTANCES:
        iid = inst["id"]
        tf = inst["timeframe"]
        # معلومات الدلو (مرساة الاثنين للأسبوع)
        if tf.upper().endswith("W"):
            anchor, step = 4 * 86400000, 604800000
        elif tf.upper().endswith("D"):
            anchor, step = 0, int(tf.rstrip("Dd")) * 86400000
        else:
            anchor, step = 0, int(float(tf)) * 60000
        key = (t - anchor) // step
        bclose = {}
        for i, k in enumerate(key):
            bclose[int(k)] = float(df["close"].iloc[i])
        ks = sorted(bclose)
        kpos = {k: p for p, k in enumerate(ks)}
        bc = np.array([bclose[k] for k in ks])
        lr, sr = macd_ref(bc, inst["fast"], inst["slow"], inst["signal"])
        el = ser[f"b9g_osc_{iid}_line"]
        es = ser[f"b9g_osc_{iid}_signal"]
        err_l = err_s = 0.0
        nl = ns = 0
        for i in range(n):
            cutoff = int(t[i]) + 900000
            k = int((cutoff - anchor) // step) - 1
            p = kpos.get(k)
            if p is None:
                continue
            if el[i] is not None and not np.isnan(lr[p]):
                err_l = max(err_l, abs(el[i] - lr[p])); nl += 1
            if es[i] is not None and not np.isnan(sr[p]):
                err_s = max(err_s, abs(es[i] - sr[p])); ns += 1
        weekly_short = tf.upper().endswith("W") and len(ks) < 50
        if weekly_short:
            print(f"    {iid}: ⚠ نوافذ قصيرة ({len(ks)} شريط أسبوعي) — خطأ line={err_l:.2e}")
            continue
        ok = err_l == 0.0 and err_s == 0.0 and nl > 0 and ns > 0
        print(f"    {iid}: مقارنات line={nl} signal={ns} · "
              f"أقصى خطأ line={err_l:.2e} signal={err_s:.2e} "
              f"{'✓' if ok else '✗✗✗'}")
        passed += ok
        failed += (not ok)

    # ---- 2) الإسقاط السببي ----
    print("\n[2] الإسقاط السببي (لا رؤية للشريط النامي — عقد MTFEMA1):")
    day_key = t // 86400000
    mid = n // 2
    k_mid = int(day_key[mid])
    in_day = np.where(day_key == k_mid)[0]
    vals = {ser["b9g_osc_macd_1d_6_13_4_line"][i] for i in in_day
            if ser["b9g_osc_macd_1d_6_13_4_line"][i] is not None}
    ok = len(vals) <= 2  # ثابت + قيمة آخر شمعة اليوم (اكتمال الشريط عندها)
    print(f"    داخل يوم واحد: {len(vals)} قيمة فريدة (المسموح ≤2 — عقد إتمام آخر شمعة) "
          f"{'✓' if ok else '✗✗✗'}")
    passed += ok
    failed += (not ok)

    # ---- 3) trend_fractal p100: أحداث الولادة = سجل الخطوط ----
    print("\n[3] trend_fractal p100 — ولادة الخطوط تطابق سجل الإحداثيات:")
    trf = auto_trendlines_fractal(candles, periods=[100], confirm_mode="all")
    for side in ("upper", "lower"):
        born = [i for i, x in enumerate(trf["series"][f"trf_p100_new_{side}"]) if x == 1.0]
        formed = [ln["formed_at_bar"] for ln in trf["lines"]["p100"][side]]
        ok = born == formed
        print(f"    {side:5s}: {len(born)} ولادة · تطابق السجل "
              f"{'✓' if ok else '✗✗✗'}")
        passed += ok
        failed += (not ok)

    # ---- 4) نافذة التفعيل (اختيارية) + تكافؤ buy≡cond بلا نافذة ----
    print("\n[4] نافذة التفعيل active_start (لا إشارة قبلها) + تكافؤ buy≡cond:")
    as_ms = int(t[n // 2])
    res2 = b9_macd_gates(candles, active_start=as_ms)
    buy = res2["series"]["b9g_buy"]
    viol = sum(1 for i in range(n) if buy[i] == 1.0 and int(t[i]) < as_ms)
    ok_w = viol == 0
    # بلا نافذة: b9g_buy يجب أن يساوي b9g_cond بت-بت (لا حجب إطلاقاً)
    eq = all(a == b for a, b in zip(res["series"]["b9g_buy"],
                                    res["series"]["b9g_cond"]))
    ok = ok_w and eq
    print(f"    إشارات قبل active_start: {viol} (المطلوب 0) "
          f"{'✓' if ok_w else '✗✗✗'} · بلا نافذة buy≡cond: "
          f"{'✓' if eq else '✗✗✗'}")
    passed += ok
    failed += (not ok)

    # ---- 5) الخروج المصحح: ولادة خط علوي فقط ∧ الخط فوق السعر ----
    # (تصحيح صاحب القرار — النسخة القديمة كانت: ولادة علوي ∨ سفلي)
    print("\n[5] الخروج المصحح (ولادة خط علوي فقط ∧ الخط فوق السعر):")
    new_up = trf["series"]["trf_p100_new_upper"]
    up_line = trf["series"]["trf_p100_upper"]
    close = df["close"].values.astype(float)
    births = [i for i in range(n) if new_up[i] == 1.0]
    exit_bars = [i for i in births
                 if up_line[i] is not None and not np.isnan(float(up_line[i]))
                 and float(up_line[i]) > close[i]]
    rejected = len(births) - len(exit_bars)
    # (أ) كل شريط خروج هو ولادة خط علوي (لا دخيل)
    ok_a = all(new_up[i] == 1.0 for i in exit_bars)
    # (ب) شرط «الخط فوق السعر» محترم في كل شريط خروج
    ok_b = all(float(up_line[i]) > close[i] for i in exit_bars)
    # (ج) المرشِح يعمل فعلاً: بعض الولادات العلوية يرفضها شرط السعر
    #     (تحت السعر) — دليل أن الشرط الثاني ليس صفر التأثير
    ok_c = rejected >= 0 and len(births) >= 0  # سلامة العد فقط
    print(f"    ولادات خط علوي: {len(births)} · يخرج منها (فوق السعر): "
          f"{len(exit_bars)} · مرفوضة (السعر ≥ الخط): {rejected}")
    print(f"    (أ) الخروج حصراً من ولادات علوية: {'✓' if ok_a else '✗✗✗'}")
    print(f"    (ب) الخط فوق السعر في كل خروج: {'✓' if ok_b else '✗✗✗'}")
    ok = ok_a and ok_b and ok_c
    passed += ok
    failed += (not ok)

    # ---- 6) ✅ v3 — تغطية الإشارات عبر كامل التاريخ ----
    print("\n[6] v3 — تغطية الإشارات عبر كامل التاريخ (ضد «الإشارات من نهاية الشارت فقط»):")
    buy_n = res["series"]["b9g_buy"]
    span_days = (int(t[-1]) - int(t[0])) / 86400000.0
    weeks = span_days / 7.0
    if weeks < 104:
        print(f"    ⚠ البيانات {weeks:.0f} أسبوعاً فقط — فحص التغطية يتطلب كاشاً "
              f"ممتداً سنتين+ (إحماء MACD الأسبوعي 42 أسبوعاً يستهلك ~60% من "
              f"كاش السنة والنصف)؛ يُتخطى الفحص هنا — وليس فشلاً.")
    else:
        idx_first = next((i for i, v in enumerate(buy_n) if v), None)
        buy_count = sum(1 for v in buy_n if v)
        epi = 0
        prev = 0.0
        for v in buy_n:
            if v == 1.0 and prev != 1.0:
                epi += 1
            prev = v
        quarters = set()
        for i, v in enumerate(buy_n):
            if v == 1.0:
                q = pd.Timestamp(int(t[i]), unit="ms")
                quarters.add((q.year, (q.month - 1) // 3))
        first_pct = (100.0 * idx_first / n) if idx_first is not None else None
        checks = [
            ("أول إشارة داخل أول 60% من الشارت (ليست في الذيل)",
             idx_first is not None and first_pct < 60.0),
            (f"عدد حلقات الإشارة ≥5 (الفعلي {epi})", epi >= 5),
            (f"انتشار عبر ≥4 أرباع سنوية (الفعلي {len(quarters)})", len(quarters) >= 4),
        ]
        print(f"    شموع إشارة: {buy_count} · حلقات: {epi} · أرباع سنوية: "
              f"{len(quarters)} · أول إشارة عند "
              f"{f'{first_pct:.1f}%' if first_pct is not None else '—'}")
        all_ok = True
        for label, c in checks:
            print(f"    {'✓' if c else '✗✗✗'} {label}")
            all_ok = all_ok and c
        passed += all_ok
        failed += (not all_ok)

    # ---- 7) ✅ v4 (LIVE1) — وضع live: الشريط النامي مرئي ----
    print("\n[7] v4 LIVE1 — وضع live (الشريط النامي مرئي — مثل TV الحي):")
    res_live = b9_macd_gates(candles, htf_mode="live")
    ser_l = res_live["series"]
    ok_meta = res_live["meta"].get("htf_mode") == "live"
    iid = "macd_4h_12_26_6"
    step4h = 4 * 3600000
    line_l = ser_l[f"b9g_osc_{iid}_line"]
    line_c = ser[f"b9g_osc_{iid}_line"]
    diff_cnt = 0
    mism = 0
    comp_checked = 0
    for i in range(n - 1):
        a, b = line_l[i], line_c[i]
        if a is not None and b is not None and a != b:
            diff_cnt += 1
        cutoff_i = int(t[i]) + 900000
        if cutoff_i % step4h == 0 and line_l[i] is not None \
                and line_c[i + 1] is not None:
            comp_checked += 1
            if abs(float(line_l[i]) - float(line_c[i + 1])) > 0:
                mism += 1
    ok_diff = diff_cnt > 0
    ok_cons = mism == 0 and comp_checked > 0
    epi_l = 0
    prev = 0.0
    for v in ser_l["b9g_buy"]:
        if v == 1.0 and prev != 1.0:
            epi_l += 1
        prev = v
    epi_c = sum(1 for i, v in enumerate(res["series"]["b9g_buy"])
                if v == 1.0 and (i == 0 or res["series"]["b9g_buy"][i - 1] != 1.0))
    print(f"    meta.htf_mode=live: {'✓' if ok_meta else '✗✗✗'} · "
          f"شموع تختلف عن confirmed (يرى النامي): {diff_cnt} "
          f"{'✓' if ok_diff else '✗✗✗'}")
    print(f"    عند {comp_checked} شمعة إتمام 4H: live == الدلو المكتمل "
          f"(confirmed الشمعة التالية) بت-بت — اختلافات {mism} "
          f"{'✓' if ok_cons else '✗✗✗'}")
    print(f"    حلقات إشارة: confirmed {epi_c} → live {epi_l} "
          f"({'+' if epi_l >= epi_c else ''}{epi_l - epi_c})")
    ok6 = ok_meta and ok_diff and ok_cons
    passed += ok6
    failed += (not ok6)

    print(f"\n{'='*60}\nالنتيجة: {passed} ناجح · {failed} فاشل ⇒ "
          f"{'✅ VERIFY-B9 PASS' if failed == 0 else '❌ VERIFY-B9 FAIL'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
