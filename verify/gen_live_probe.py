#!/usr/bin/env python3
"""R76 — إعادة توليد مسبار الإنتاج الحي /tmp/live_osc_probe.json.

يقيس سلاسل الموشرات (MACD/RSI/MOM) من الإنتاج الحي (161.97.73.254:8000)
على 400 شمعة 1m اصطناعية (seed=42) بنفس عقد PRO73 (osc_instances عبر
POST /api/overlays/compute). الإنتاج غير مرقّع ⇒ إشارة MACD هناك EMA
(القديمة) — وهذا بالضبط ما تحتاجه بطارية T2 لإثبات تغيير B-4 (SMA).
"""
import json
import urllib.request

import numpy as np

BASE = "http://161.97.73.254:8000/api/v1/overlays/compute"

# 400 شمعة 1m اصطناعية (seed=42) — نفس منهجية المسبار الأصلي
rng = np.random.default_rng(42)
n = 400
price = 100.0
candles = []
t0 = 1777593540000  # نفس نقطة البداية في البطارية
for i in range(n):
    o = price
    c = o + rng.normal(0.05, 0.3)
    h = max(o, c) + abs(rng.normal(0, 0.1))
    lo = min(o, c) - abs(rng.normal(0, 0.1))
    candles.append({"time": t0 + i * 60_000, "open": float(o), "high": float(h),
                    "low": float(lo), "close": float(c), "volume": float(rng.uniform(50, 300))})
    price = c

body = {
    "candles": candles,
    "types": ["zigzag_fib_e2e_trendy_macd"],
    "params": {"zigzag_fib_e2e_trendy_macd": {
        "osc_instances": [
            {"kind": "macd", "id": "macd_1m_6_13_4", "timeframe": "1m",
             "fast": 6, "slow": 13, "signal": 4},
            {"kind": "rsi", "id": "rsi_1m_14_14", "timeframe": "1m",
             "period": 14, "ma_length": 14, "bb_std": 2},
            {"kind": "mom", "id": "mom_1m_10", "timeframe": "1m", "length": 10},
        ],
    }},
}

req = urllib.request.Request(
    BASE, data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=60) as r:
    resp = json.loads(r.read().decode())

ov = resp["overlays"]["zigzag_fib_e2e_trendy_macd"]
series = ov["series"]
probe = {
    "source": "live-production-161.97.73.254:8000",
    "measured_at": "2026-11-15",
    "endpoint": "POST /api/overlays/compute · zigzag_fib_e2e_trendy_macd",
    "closes": [c["close"] for c in candles],
    "series": {k: v for k, v in series.items() if "_osc_" in k},
}
with open("/tmp/live_osc_probe.json", "w") as f:
    json.dump(probe, f)

keys = sorted(probe["series"].keys())
print(f"closes: {len(probe['closes'])} · series keys: {len(keys)}")
for k in keys:
    print(" ", k)
print("osc section:", json.dumps({k: v for k, v in ov.get("osc", {}).items()
                                  if k in ("engine", "version", "base_tf", "instances")},
                                  ensure_ascii=False)[:400])
