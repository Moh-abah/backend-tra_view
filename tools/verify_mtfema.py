#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""التحقق النهائي بعد نشر حزمة MTF EMA (المتوسط الأسي متعدد الفريمات).

يسلّم حمولة التحقق (نافذة القاعدة الكمومية + MTF EMA للرسم فقط) إلى الباك
اند الحي، يستطلعها حتى الاكتمال، ثم يحقق:
  1) المؤشر مسجل: mtf_ema يظهر في /api/v1/indicators/available (اختياري —
     يعمل حتى لو أخفته صيغة الاستجابة؛ الحسم بالأعمدة).
  2) مقاييس الكمومية == المرجعية بت-بت (+69.338535% · 31 صفقة · PF 1.978685)
     — MTF EMA لم يمس قراراً واحداً (رسم فقط، بلا شروط).
  3) عمود الرسم ind_mtfema_value موجود في كل شمعة (null مسموح في الإحماء
     فقط) — مع ind_mtfema_main (النسخة الضمنية "main").
  4) ✅ الذهبي: القيم مطابقة بت-بت لمرجع مستقل يُحسب من شموع الرد نفسها
     (تجميع 60m ثم EMA100 ببذرة SMA ثم المحاذاة السببية آخر-شريط-مغلق).
  5) (اختياري --multi) نسخ متعددة: ind_mtfema_fast/slow/day كلها موجودة
     ومطابقة للمرجع المستقل.

الاستخدام:
  python3 verify_mtfema.py [SERVER]            # الحمولة الأساسية
  python3 verify_mtfema.py [SERVER] --multi   # حمولة النسخ الثلاث
"""
import bisect
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

SERVER = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
    else "http://161.97.73.254:8000"
MULTI = "--multi" in sys.argv[1:]

PAYLOAD_FILE = ("payloads/mtfema_multi_payload.json" if MULTI
                else "payloads/mtfema_verify_payload.json")

EXPECTED = {
    "total_pnl_percent": 69.338535135082,
    "total_trades": 31,
    "winning_trades": 27,
    "losing_trades": 4,
    "win_rate": 87.09677419354838,
    "profit_factor": 1.978684961471487,
}
TOL = 1e-9


def _get(path, timeout=900):
    req = urllib.request.Request(SERVER + path,
                                 headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        enc = r.headers.get("Content-Encoding")
    if enc == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    return json.JSONDecoder().raw_decode(raw.decode("utf-8"))[0]


def _post(path, payload, timeout=120):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        SERVER + path, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        enc = r.headers.get("Content-Encoding")
    if enc == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# المرجع المستقل — يُحسب من شموع الرد نفسها (صفر ثقة بالكود المنشور)
# ---------------------------------------------------------------------------
def ref_mtf_ema(candles, resolution_min, length, source="close", offset=0):
    if not candles:
        return []
    base_step = _to_ms(candles[1]["timestamp"]) - _to_ms(candles[0]["timestamp"]) \
        if len(candles) > 1 else 15 * 60 * 1000
    htf_step = resolution_min * 60 * 1000
    ts = [_to_ms(c["timestamp"]) for c in candles]
    N = len(candles)
    buckets, order = {}, []
    for i in range(N):
        k = ts[i] // htf_step
        if k not in buckets:
            buckets[k] = {"o": float(candles[i]["open"]),
                         "h": float(candles[i]["high"]),
                         "l": float(candles[i]["low"]),
                         "c": float(candles[i]["close"])}
            order.append(k)
        else:
            b = buckets[k]
            b["h"] = max(b["h"], float(candles[i]["high"]))
            b["l"] = min(b["l"], float(candles[i]["low"]))
            b["c"] = float(candles[i]["close"])
    keys = sorted(buckets)
    smap = {"close": "c", "open": "o", "high": "h", "low": "l"}
    if source == "hl2":
        sv = [(buckets[k]["h"] + buckets[k]["l"]) / 2 for k in keys]
    elif source == "hlc3":
        sv = [(buckets[k]["h"] + buckets[k]["l"] + buckets[k]["c"]) / 3
              for k in keys]
    elif source == "ohlc4":
        sv = [(buckets[k]["o"] + buckets[k]["h"] + buckets[k]["l"] + buckets[k]["c"]) / 4
              for k in keys]
    else:
        sv = [buckets[k][smap[source]] for k in keys]
    hcm = [(k + 1) * htf_step for k in keys]
    M = len(sv)
    ema = [None] * M
    if M >= length:
        seed = sum(sv[:length]) / length
        ema[length - 1] = seed
        alpha = 2.0 / (length + 1.0)
        prev = seed
        for j in range(length, M):
            prev = alpha * sv[j] + (1 - alpha) * prev
            ema[j] = prev
    out = [None] * N
    for i in range(N):
        j = bisect.bisect_right(hcm, ts[i] + base_step) - 1
        if j >= 0 and ema[j] is not None:
            out[i] = ema[j]
    if offset > 0:
        out = [None] * offset + out[:N - offset] if offset < N else [None] * N
    return out


def _to_ms(ts):
    s = str(ts).replace("Z", "+00:00")
    return int(datetime.fromisoformat(s).timestamp() * 1000)


def cmp(a, b):
    d, first = 0, None
    for i, (x, y) in enumerate(zip(a, b)):
        if x is None and y is None:
            continue
        if x is None or y is None:
            d += 1
            first = first or (i, x, y)
            continue
        if abs(float(x) - float(y)) > 1e-9:
            d += 1
            first = first or (i, x, y)
    return d, first


def main():
    payload = json.load(open(PAYLOAD_FILE, encoding="utf-8"))
    payload["name"] = payload["name"] + f" · {datetime.utcnow():%H:%M:%S}"

    print("=" * 80)
    print("التحقق بعد نشر MTF EMA — المتوسط الأسي متعدد الفريمات (+ الكمومية)")
    print(f"السيرفر: {SERVER} · الحمولة: {'نسخ متعددة' if MULTI else 'أساسية'}")
    print("=" * 80)

    # 1) التسجيل في قائمة المؤشرات المتاحة (اختياري)
    try:
        avail = _get("/api/v1/indicators/available", timeout=60)
        lst = avail if isinstance(avail, list) else (avail.get("indicators")
                                                      or avail.get("data") or [])
        names = {str(x.get("name", "")).lower() for x in lst if isinstance(x, dict)}
        has = "mtf_ema" in names or "mtfema" in names
        print(f"\n[0] mtf_ema في /indicators/available: {'✓' if has else '⚠ (استجابة غير قياسية — الحسم بالأعمدة)'}")
    except Exception as e:
        print(f"\n[0] تعذر جلب القائمة ({e}) — الحسم بالأعمدة")

    # 2) تسليم الحمولة
    print("\n[1] تسليم حمولة التحقق …", flush=True)
    disp = _post("/api/v1/backtest1/run", payload)
    if not disp.get("success"):
        print("  فشل التسليم:", json.dumps(disp, ensure_ascii=False)[:400])
        return 2
    task_id = str(disp.get("task_id"))
    print(f"  المهمة: {task_id}")

    # 3) الاستطلاع
    t0 = time.time()
    while True:
        try:
            st = _get(f"/api/v1/backtest1/status/{task_id}", timeout=60)
        except urllib.error.HTTPError as e:
            print(f"  [poll] HTTP {e.code} — إعادة محاولة")
            time.sleep(5)
            continue
        state = st.get("state") or st.get("status")
        if state in ("SUCCESS", "completed"):
            break
        if state in ("FAILURE", "failed", "REVOKED"):
            print("  فشلت المهمة:", str(st.get("error"))[:400])
            return 2
        if time.time() - t0 > 1500:
            print("  انتهت المهلة")
            return 3
        if (time.time() - t0) % 20 < 4.5:
            print(f"  [{time.time()-t0:5.1f}s] state={state}", flush=True)
        time.sleep(4)
    print(f"  اكتملت خلال {time.time()-t0:.1f}s")
    bid = st.get("backtest_id") or disp.get("backtest_id")

    # 4) الجلب والتحقق
    print("\n[2] جلب الرد الكامل …", flush=True)
    res = _get(f"/api/v1/backtest1/get/{bid}")
    cd = res.get("chart_data") or {}
    vc = cd.get("visual_candles") or []
    s = res.get("summary") or {}
    print(f"  الشموع: {len(vc)}")

    print("\n[3] مقاييس الكمومية (MTF EMA لم يمس قراراً):")
    ok_m = True
    for k, exp in EXPECTED.items():
        got = s.get(k)
        good = got is not None and abs(float(got) - float(exp)) <= TOL
        ok_m = ok_m and good
        print(f"  {'✓' if good else '✗'} {k}: {got} (متوقع {exp})")

    print("\n[4] أعمدة الرسم ind_mtfema_*:")
    mcols = sorted(k for k in (vc[0] or {}) if k.startswith("ind_mtfema_")) \
        if vc else []
    print(f"  الموجودة: {mcols}")
    need = ["ind_mtfema_value"] + ([] if MULTI else ["ind_mtfema_main"]) + \
        (["ind_mtfema_fast", "ind_mtfema_slow", "ind_mtfema_day"] if MULTI else [])
    missing = [c for c in need if c not in mcols]
    print(f"  {'✓' if not missing else '✗'} الأعمدة المطلوبة كلها موجودة"
          + (f" — ناقص: {missing}" if missing else ""))

    spec = ([(60, 21, "close", "ind_mtfema_fast"),
             (240, 100, "close", "ind_mtfema_slow"),
             (1440, 50, "hlc3", "ind_mtfema_day")] if MULTI
            else [(60, 100, "close", "ind_mtfema_value")])

    ok_v = True
    for reso_min, length, source, col in spec:
        got = [c.get(col) for c in vc]
        exp = ref_mtf_ema(vc, reso_min, length, source=source)
        d, first = cmp(got, exp)
        nn = sum(1 for v in got if v is not None)
        ok = d == 0
        ok_v = ok_v and ok
        print(f"  {'✓' if ok else '✗'} {col} (EMA{length}@{reso_min}m{'' if source=='close' else ' '+source}): "
              f"{'بت-بت ضد مرجع مستقل محسوب من شموع الرد' if ok else f'{d} فرق (أول: {first})'} "
              f"({nn}/{len(vc)} قيمة)")

    # الحكم
    ok = ok_m and ok_v and not missing
    print("\n" + "=" * 80)
    print("الحكم النهائي:",
          "✓✓✓ نشر MTF EMA مكتمل وسليم — الرسم يعمل والقيم مرجعية بت-بت "
          "والكمومية لم تتأثر إطلاقاً"
          if ok else "!! راجع البنود أعلاه")
    print("=" * 80)
    json.dump({
        "server": SERVER, "task_id": task_id, "backtest_id": bid,
        "multi": MULTI, "candles": len(vc), "columns": mcols,
        "metrics_match": ok_m, "values_match": ok_v, "missing": missing,
        "verdict": ok,
    }, open("verify_mtfema_result.json", "w"), ensure_ascii=False, indent=1)
    print("[saved] verify_mtfema_result.json — backtest_id:", bid)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
