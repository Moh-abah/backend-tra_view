# -*- coding: utf-8 -*-
"""
ROUND32 — الطور D: اختبار مسارات HTTP الحقيقية (الخادم الفعلي على :8000)
=========================================================================
1) GET  /overlays/compute  → trend_fractal (إحداثيات الخطوط) + zzfib_e2e_trendy (الأعمدة)
2) GET  /live/strategy/signal → الإشارة الحية للترندية على 6 عملات × فريمات
   + مقارنة E2E على نفس الخلايا (نفس اللحظة — من الكاش الحي)
3) زمن الاستجابة لكل نداء (أداء الإنتاج الحقيقي)
"""
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

BASE = "http://127.0.0.1:8000"
OUT = "/home/z/my-project/download/ROUND32-E2E-TRENDY/evidence/realtest"
K3 = timezone(timedelta(hours=3))

RES = {"meta": {"started_at": datetime.now(K3).isoformat(), "base": BASE}, "http": []}


def get(path, params=None, timeout=120):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return body, ms, None
    except Exception as e:  # noqa: BLE001
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return None, ms, f"{type(e).__name__}: {str(e)[:200]}"


def save():
    with open(f"{OUT}/http_results.json", "w", encoding="utf-8") as f:
        json.dump(RES, f, ensure_ascii=False, indent=1, default=str)


print("=== 1) /overlays/compute — trend_fractal (BTCUSDT 1m) ===", flush=True)
body, ms, err = get("/api/v1/overlays/compute", {
    "symbol": "BTCUSDT", "timeframe": "1m", "days": 1, "types": "trend_fractal"})
rec = {"test": "compute_trend_fractal", "symbol": "BTCUSDT", "timeframe": "1m",
       "ms": ms, "error": err}
if body:
    tfd = (body.get("overlays") or {}).get("trend_fractal") or {}
    p = tfd.get("params") or {}
    lines = tfd.get("lines") or {}
    rec["params"] = p
    rec["lines_by_period"] = {k: len(v.get("upper", [])) + len(v.get("lower", []))
                              for k, v in lines.items() if isinstance(v, dict)}
    last_key = sorted(lines.keys())[-1] if lines else None
    last_line = (lines.get(last_key) or {}).get("upper", [None])[-1] if last_key else None
    rec["sample_line"] = last_line
    rec["summary"] = body.get("summary")
    print(f"  OK {ms}ms — periods={p.get('periods')} lines={rec['lines_by_period']}", flush=True)
    print(f"  sample: {json.dumps(rec['sample_line'], ensure_ascii=False)[:260]}", flush=True)
else:
    print(f"  FAIL {ms}ms — {err}", flush=True)
RES["http"].append(rec)
save()

print("=== 2) /overlays/compute — zzfib_e2e_trendy (BTCUSDT 1m) ===", flush=True)
body, ms, err = get("/api/v1/overlays/compute", {
    "symbol": "BTCUSDT", "timeframe": "1m", "days": 1, "types": "zzfib_e2e_trendy"})
rec = {"test": "compute_zzfib_e2e_trendy", "symbol": "BTCUSDT", "timeframe": "1m",
       "ms": ms, "error": err}
if body:
    tz = (body.get("overlays") or {}).get("zzfib_e2e_trendy") or {}
    p = tz.get("params") or {}
    series = tz.get("series") or {}
    trend = tz.get("trend") or {}
    rec["params"] = p
    rec["series_keys_n"] = len(series or {})
    rec["has_gate_columns"] = all(k in (series or {}) for k in
                                  ("zzfet_entry_raw_s1", "zzfet_entry_s1",
                                   "zzfet_entry_blocked_s1", "zzfet_trend_ok"))
    rec["trend_periods"] = trend.get("periods")
    rec["trend_lines_count"] = len(trend.get("lines") or {})
    rec["summary"] = body.get("summary")
    print(f"  OK {ms}ms — series={rec['series_keys_n']} gate_cols={rec['has_gate_columns']} "
          f"lines={rec['trend_lines_count']}", flush=True)
else:
    print(f"  FAIL {ms}ms — {err}", flush=True)
RES["http"].append(rec)
save()

print("=== 3) /live/strategy/signal — الترندية على 6 عملات × فريمات ===", flush=True)
LIVE_MATRIX = [
    ("BTCUSDT", "1m"), ("ETHUSDT", "5m"), ("SOLUSDT", "15m"),
    ("BNBUSDT", "1h"), ("XRPUSDT", "4h"), ("RUNEUSDT", "1m"),
]
for sym, tf in LIVE_MATRIX:
    body, ms, err = get("/api/v1/live/strategy/signal", {
        "symbol": sym, "market": "crypto", "timeframe": tf,
        "strategy": "zigzag_fib_e2e_trendy"})
    rec = {"test": "live_trendy", "symbol": sym, "timeframe": tf, "ms": ms, "error": err}
    if body:
        d = body.get("data") or body
        meta = d.get("meta") or {}
        sig = d.get("signal") or None
        rec["engine"] = meta.get("engine")
        rec["state"] = d.get("state")
        rec["has_signal"] = bool(d.get("has_signal"))
        rec["signal_label"] = (sig or {}).get("label")
        rec["invalidated_by"] = d.get("invalidated_by")
        rec["params_applied"] = meta.get("params_applied")
        rec["evaluation_ms"] = meta.get("evaluation_ms")
        print(f"  {sym} {tf}: {ms}ms state={rec['state']} signal={rec['signal_label']} "
              f"engine={(rec['engine'] or '')[:40]}", flush=True)
    else:
        print(f"  {sym} {tf}: FAIL {ms}ms — {err}", flush=True)
    RES["http"].append(rec)
    save()

print("=== 4) المقارنة الحية — نفس اللحظة: E2E مقابل الترندية (4 خلايا) ===", flush=True)
for sym, tf in [("BTCUSDT", "1m"), ("ETHUSDT", "1h"), ("SOLUSDT", "15m"), ("RUNEUSDT", "1m")]:
    b_e2e, m1, e1 = get("/api/v1/live/strategy/signal", {
        "symbol": sym, "market": "crypto", "timeframe": tf, "strategy": "zigzag_fib_e2e"})
    b_tr, m2, e2 = get("/api/v1/live/strategy/signal", {
        "symbol": sym, "market": "crypto", "timeframe": tf, "strategy": "zigzag_fib_e2e_trendy"})
    rec = {"test": "live_compare", "symbol": sym, "timeframe": tf,
           "e2e_ms": m1, "trendy_ms": m2, "e2e_error": e1, "trendy_error": e2}
    if b_e2e:
        d = b_e2e.get("data") or b_e2e
        rec["e2e_state"] = d.get("state")
        rec["e2e_signal"] = (d.get("signal") or {}).get("label")
        rec["e2e_engine"] = (d.get("meta") or {}).get("engine")
    if b_tr:
        d = b_tr.get("data") or b_tr
        rec["trendy_state"] = d.get("state")
        rec["trendy_signal"] = (d.get("signal") or {}).get("label")
        rec["trendy_engine"] = (d.get("meta") or {}).get("engine")
        rec["trendy_params"] = (d.get("meta") or {}).get("params_applied")
    print(f"  {sym} {tf}: E2E={rec.get('e2e_state')}({rec.get('e2e_signal')}) vs "
          f"TRENDY={rec.get('trendy_state')}({rec.get('trendy_signal')})", flush=True)
    RES["http"].append(rec)
    save()

RES["meta"]["finished_at"] = datetime.now(K3).isoformat()
save()
print("\nHTTP PHASE DONE", flush=True)
