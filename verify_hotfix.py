#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""أداة إعادة التحقق بعد نشر الإصلاح — تعمل على السيرفر الحي مباشرة.

تشغّل نفس فحص البطارية الذي كشف الخلل:
  POST /api/v1/overlays/compute مع شموع كاملة (9,660) للمحرك الجديد —
  يجب أن يعيد 200 بعد الإصلاح (كان 500 بسبب np.int64 في أحداث الرصة).

الاستخدام: python3 verify_hotfix.py [SERVER]
"""
import gzip
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime

SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://161.97.73.254:8000"
CANDLES = "/home/z/my-project/download/candles_10000407.json"


def main() -> int:
    candles = json.load(open(CANDLES))
    conv = []
    for c in candles:
        dt = datetime.fromisoformat(c["timestamp"].replace("Z", "+00:00"))
        conv.append({
            "time": int(dt.timestamp() * 1000),
            "open": c["open"], "high": c["high"],
            "low": c["low"], "close": c["close"],
            "volume": c.get("volume", 0),
        })

    payload = {
        "candles": conv,
        "types": ["zzfib_e2e_trendy_quantum_ema"],
        "params": {"zzfib_e2e_trendy_quantum_ema": {
            "mode": "luxalgo", "length": 100,
            "trend_periods": [7, 15, 25], "trend_confirm": "majority",
            "trend_gate": ["s1", "s2", "s3"], "zone_gate": ["s1", "s2", "s3"],
            "ema_lengths": [21, 50, 100, 200, 350, 500],
            "ema_resolution": "60", "ema_source": "close",
            "ema_offset": 0, "ema_gate": ["s1", "s2", "s3"],
        }},
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        SERVER + "/api/v1/overlays/compute",
        data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept-Encoding": "gzip"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
    except urllib.error.HTTPError as e:
        print(f"✘ FAILED — HTTP {e.code}: المحرك ما زال يكسر overlays/compute")
        print("   جرّب قراءة سجل الخطأ في السيرفر (np.int64 غير قابلة للتسلسل).")
        return 2

    d = json.loads(raw)
    ov = (d.get("overlays") or {}).get("zzfib_e2e_trendy_quantum_ema") or {}
    ema = ov.get("ema") or {}
    counts = ema.get("counts") or {}
    series = ov.get("series") or {}
    n_qe = sum(1 for k in series if str(k).startswith("zzfetqe_"))
    ok = (
        len(ov.get("signals") or []) > 0
        and counts.get("stack_enters") == 42
        and counts.get("stack_exits") == 41
        and counts.get("stack_ok_bars") == 690
        and counts.get("final_entries") == 16
        and counts.get("ema_blocked") == 13
        and n_qe == 75
    )
    print(f"✔ overlays/compute 200 · bars={d.get('summary', {}).get('bars')}")
    print(f"  zzfetqe series: {n_qe} (عقد 75)")
    print(f"  ema.counts: {json.dumps(counts, ensure_ascii=False)}")
    print(f"  أحداث الرصة: {len(ema.get('events') or [])} · أول وقت: "
          f"{(ema.get('events') or [{}])[0].get('time')}")
    print("✔✔ الإصلاح منشور ويعمل — البطارية كاملة" if ok else "⚠ تحقق من الأرقام أعلاه")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
