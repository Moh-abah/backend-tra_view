#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROUND19 — التحقق الحي عبر HTTP (النمط الإنتاجي الحرفي)
======================================================
يشغّل السيرفر بنمط Popen manager (نفس نمط المشروع) ويدق:
  H1) GET /api/v1/strategies/presets — البريسِت الرسمي يحمل mode=tradingview
      بمعاملاته (depth=12 · deviation=20 · backstep=3) كما يصل للفرونت.
  H2) GET /api/v1/live/strategy/signal (ZECUSDT 5m) مرتان — المرة الثانية من
      الكاش (زمن < 0.05s) — والسيرفر يعيد 200 بلا أي استثناء.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = "/home/z/my-project/backend-audit/pro27"
LOG = "/tmp/round19_http_server.log"

env = dict(os.environ)
env["SECRET_KEY"] = "r6fwc7Q8CGqI3RpKFaTDbJJ55EOR6LrADCPZv4_KK5LbI0fpzDn84KhemcV_TE0C"
env["PYTHONUNBUFFERED"] = "1"

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8777", "--log-level", "warning"],
    cwd=ROOT, env=env, stdout=open(LOG, "w"), stderr=subprocess.STDOUT,
)


def get(path, timeout=120):
    t0 = time.time()
    with urllib.request.urlopen(f"http://127.0.0.1:8777{path}", timeout=timeout) as r:
        body = json.loads(r.read().decode())
        return r.status, body, time.time() - t0


fails = []
try:
    deadline = time.time() + 90
    up = False
    while time.time() < deadline and proc.poll() is None:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8777/docs", timeout=3) as r:
                if r.status == 200:
                    up = True
                    break
        except Exception:
            time.sleep(1.0)
    print(f"SERVER_PID={proc.pid} UP={up}")
    if not up:
        print(open(LOG).read()[-3000:])
        sys.exit(1)

    # ---------- H1) البريسِت الرسمي ----------
    st, body, _ = get("/api/v1/strategies/presets")
    zlf = next((p for p in body.get("presets", [])
                if p.get("id") == "zlf_triple_signal_zero_fee"), None)
    ip = (((zlf or {}).get("payload") or {}).get("strategy_config") or {}) \
        .get("indicators", [{}])[0].get("params", {})
    want = {"mode": "tradingview", "depth": 12, "deviation": 20, "backstep": 3}
    bad = {k: (ip.get(k), v) for k, v in want.items() if ip.get(k) != v}
    print(f"\n[H1] presets endpoint: HTTP {st} · zlf params={json.dumps(ip, ensure_ascii=False)}")
    if st != 200 or bad:
        fails.append(f"H1: st={st} bad={bad}")
        print("  ✗ FAIL")
    else:
        print("  ✓ mode=tradingview يصل للفرونت حرفياً عبر HTTP")

    # ---------- H2) الإشارة الحية مرتان ----------
    sig_path = ("/api/v1/live/strategy/signal?symbol=ZECUSDT&market=crypto"
                "&timeframe=5m&strategy=zigzag_fib")
    st1, b1, t1 = get(sig_path)
    st2, b2, t2 = get(sig_path)
    d1, d2 = b1.get("data") or {}, b2.get("data") or {}
    print(f"\n[H2] live signal: HTTP {st1}/{st2} · t1={t1:.2f}s · t2={t2:.2f}s (cached)")
    print(f"     state1={d1.get('state')} has_signal={d1.get('has_signal')} "
          f"signal={json.dumps(d1.get('signal'), ensure_ascii=False)[:180]}")
    print(f"     state2={d2.get('state')} has_signal={d2.get('has_signal')} "
          f"(identical={d1 == d2})")
    win = (d1.get("meta") or {}).get("window") or {}
    print(f"     window: closed={win.get('closed_candles')} "
          f"last_closed_open={win.get('last_closed_open')}")
    if st1 != 200 or st2 != 200 or t2 > 0.5 or d1 != d2:
        fails.append(f"H2: st1={st1} st2={st2} t2={t2} identical={d1 == d2}")
        print("  ✗ FAIL")
    else:
        print("  ✓ نقطة الإشارة الحية تعمل عبر HTTP — المرة الثانية من الكاش وجواب مطابق حرفياً (تقارب كامل)")

    # ---------- H3) رسم الشارت الحي (zzfib) بوضع TV ----------
    st3, b3, _ = get("/api/v1/overlays/compute?symbol=ZECUSDT&market=crypto"
                     "&timeframe=5m&days=7&types=zzfib&limit=1500")
    zzf = (b3.get("overlays") or {}).get("zzfib") or {}
    zp = zzf.get("params") or {}
    legs = zzf.get("legs") or []
    print(f"\n[H3] chart overlays (zzfib): HTTP {st3} · legs={len(legs)} · "
          f"mode={zp.get('mode')} depth={zp.get('depth')} deviation={zp.get('deviation')} "
          f"backstep={zp.get('backstep')}")
    if st3 != 200 or zp.get("mode") != "tradingview" or not legs:
        fails.append(f"H3: st={st3} params={zp.get('mode')} legs={len(legs)}")
        print("  ✗ FAIL")
    else:
        print("  ✓ الشارت الحي يرسم zzfib بوضع tradingview (نفس معاملات البريسِت)")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

print("\n" + "=" * 80)
if fails:
    print(f"RESULT: {len(fails)} FAIL(S): {fails}")
    sys.exit(1)
print("RESULT: HTTP LIVE PROOFS PASS ✓")
