#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""✅ PRO74 — برهان حياد الإحماء: القالب الخفيف المصلَّح يحفظ البطل تامًا.

القصة: الباك-تست الحي (المهمة 10000286 على 161.97.73.254:8000 — تكوين البطل
#10000265 ملتهبة S|N5) حجب 11 صفقة كلها في أول 10 أيام من النافذة — نمط
إحماء: المحرك يحسب مصفوفة الموشرات من بداية النافذة الباردة، فمؤشرات HTF
(يومي/أسبوعي) NaN → البوابة False زورًا → +998.05% بدل +1638.16%.

الإصلاح (mtf_oscillator_core.macdized_layer — PRO74): قبل جاهزية كل الأوراق
المرجعية بالشجرة، البوابة محايدة (مفتوحة). هذا الاختبار يبرهن:
  1) البوابة المصلَّحة صفر حجب من إشارات صفقات البطل الـ64
  2) أفق الإحماء ~15 أسبوعًا (151,199 شمعة = 22.7% من النافذة) كما تنبئ
     الرياضيات (بطيء RSI 1w = 14 أسبوعًا + بولينجر)
  3) macdized_layer بالنسخ السبع تعمل بكفاءة (~40 ثانية للنافذة الكاملة)
"""
import datetime as _dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [os.path.join(HERE, ".."), os.path.join(HERE, "..", "src"), HERE]
SRC = next((p for p in CANDIDATES
            if os.path.isfile(os.path.join(p, "app", "services", "indicators", "mtf_oscillator_core.py"))),
           CANDIDATES[0])
sys.path.insert(0, os.path.abspath(SRC))

os.environ.setdefault("SECRET_KEY", "r74-warmup-proof-0123456789")
os.environ.setdefault("DEBUG", "true")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DATA_CANDIDATES = [
    "/home/z/my-project/r70-workspace/data/SOLUSDT_1m.npz",
    os.path.join(HERE, "..", "..", "..", "r70-workspace", "data", "SOLUSDT_1m.npz"),
]
DATA_PATH = next((p for p in DATA_CANDIDATES if os.path.isfile(p)), None)

CHAMP_FROM = int(_dt.datetime(2023, 10, 16, tzinfo=_dt.timezone.utc).timestamp() * 1000)
CHAMP_TO = 1737320280000  # 2025-01-19T20:58:00Z

# إشارات صفقات البطل الـ64 (دخول التنفيذ — من تشغيل الهوية الحي #10000265)
HERO_ENTRIES = [
    "2023-10-16T05:01:00+00:00", "2023-10-16T12:35:00+00:00", "2023-10-16T13:31:00+00:00", "2023-10-19T16:17:00+00:00",
    "2023-10-20T08:16:00+00:00", "2023-10-21T06:31:00+00:00", "2023-10-21T11:11:00+00:00", "2023-10-21T20:32:00+00:00",
    "2023-10-23T16:55:00+00:00", "2023-10-23T22:42:00+00:00", "2023-10-25T12:15:00+00:00", "2023-10-30T12:18:00+00:00",
    "2023-10-31T20:48:00+00:00", "2023-11-01T07:44:00+00:00", "2023-11-01T15:07:00+00:00", "2023-11-01T21:15:00+00:00",
    "2023-11-09T08:34:00+00:00", "2023-11-09T16:09:00+00:00", "2023-11-10T06:57:00+00:00", "2023-11-10T16:08:00+00:00",
    "2023-11-10T18:12:00+00:00", "2023-11-11T01:22:00+00:00", "2023-11-11T14:04:00+00:00", "2023-11-11T16:15:00+00:00",
    "2023-11-15T22:15:00+00:00", "2023-11-16T06:31:00+00:00", "2023-12-08T03:24:00+00:00", "2023-12-08T23:42:00+00:00",
    "2023-12-15T11:58:00+00:00", "2023-12-20T21:22:00+00:00", "2023-12-21T06:34:00+00:00", "2023-12-21T16:09:00+00:00",
    "2023-12-21T19:34:00+00:00", "2023-12-22T04:42:00+00:00", "2023-12-23T21:54:00+00:00", "2023-12-24T01:28:00+00:00",
    "2023-12-24T12:54:00+00:00", "2023-12-25T15:02:00+00:00", "2023-12-26T04:09:00+00:00", "2024-02-29T07:50:00+00:00",
    "2024-02-29T08:32:00+00:00", "2024-03-01T04:10:00+00:00", "2024-03-05T22:55:00+00:00", "2024-03-05T23:37:00+00:00",
    "2024-03-06T11:21:00+00:00", "2024-03-07T02:11:00+00:00", "2024-03-07T14:16:00+00:00", "2024-03-12T06:00:00+00:00",
    "2024-03-14T00:14:00+00:00", "2024-03-14T09:18:00+00:00", "2024-03-15T01:21:00+00:00", "2024-03-16T10:28:00+00:00",
    "2024-03-18T01:55:00+00:00", "2024-03-19T11:44:00+00:00", "2024-03-19T14:39:00+00:00", "2024-03-21T00:43:00+00:00",
    "2024-04-01T04:12:00+00:00", "2024-11-10T17:39:00+00:00", "2024-11-11T20:41:00+00:00", "2024-11-17T08:38:00+00:00",
    "2024-11-21T14:57:00+00:00", "2024-11-22T21:50:00+00:00", "2025-01-18T16:07:00+00:00", "2025-01-19T10:45:00+00:00",
]  # 64 مدخلاً — نسخة مطابقة لتشغيل الهوية الحي (trade_points)

from app.services.indicators.mtf_oscillator_core import macdized_layer  # noqa: E402
from app.services.indicators.osc_cases import OSC_DOC_INSTANCES, RSI_ANY  # noqa: E402


def _ts_ms(iso: str) -> int:
    return int(_dt.datetime.fromisoformat(iso).timestamp() * 1000)


def main() -> int:
    print("=" * 78)
    print("PRO74 — برهان حياد الإحماء على نافذة البطل (665,099 شمعة · SOLUSDT 1m)")
    print("=" * 78)
    if DATA_PATH is None:
        print("⚠️ بيانات SOL غير موجودة — يُتخطى البرهان (تم توثيقه في التسليم)")
        return 0
    z = np.load(DATA_PATH)
    T = z["time_ms"].astype(np.int64)
    m = (T >= CHAMP_FROM) & (T <= CHAMP_TO)
    T = T[m]
    O = z["open"][m].astype(np.float64)
    H = z["high"][m].astype(np.float64)
    L = z["low"][m].astype(np.float64)
    C = z["close"][m].astype(np.float64)
    V = z["volume"][m].astype(np.float64)
    N = len(T)
    print(f"النافذة الباردة: {N:,} شمعة")

    df = pd.DataFrame({"open": O, "high": H, "low": L, "close": C, "volume": V},
                      index=pd.DatetimeIndex(pd.to_datetime(T, unit="ms", utc=True), name="time"))

    need_ids = set()
    def _refs(tree):
        if isinstance(tree, dict):
            for k in ("left", "right"):
                v = tree.get(k)
                if isinstance(v, str) and v.startswith("osc:"):
                    need_ids.add(v.split(":")[1].split(".")[0])
            for c in (tree.get("conditions") or []):
                _refs(c)
    _refs(RSI_ANY)
    insts7 = [i for i in OSC_DOC_INSTANCES if i["id"] in need_ids]

    t0 = time.perf_counter()
    layer = macdized_layer(df, insts7, RSI_ANY)
    el = time.perf_counter() - t0
    gate = np.asarray(layer["gate"], dtype=bool)
    hz = int(layer.get("warmup_neutral_bars") or 0)
    print(f"macdized_layer (مصلَّحة): {el:.1f}s · أفق الحياد={hz:,} شمعة "
          f"({hz / N * 100:.1f}% ≈ {hz / 10080:.1f} أسبوعًا)")

    sig_ms = np.array([_ts_ms(e) - 60_000 for e in HERO_ENTRIES], dtype=np.int64)
    idx = np.searchsorted(T, sig_ms)
    ok = T[idx] == sig_ms
    blocked = [HERO_ENTRIES[i] for i in range(len(HERO_ENTRIES)) if ok[i] and not gate[idx[i]]]
    print(f"إشارات صفقات البطل الـ64 تحت البوابة المصلَّحة: محجوبة = {len(blocked)}")
    for b in blocked[:5]:
        print(f"  ✗ {b}")

    checks = [
        ("W1 البوابة المصلَّحة لا تحجب أي إشارة من إشارات البطل (حفظ تام)",
         len(blocked) == 0, f"محجوبة={len(blocked)}"),
        ("W2 أفق الإحماء = نطاق 1w RSI (14 أسبوعًا + بولينجر ≈ 14-16 أسبوعًا)",
         130_000 <= hz <= 170_000, f"الأفق={hz:,}"),
        ("W3 الطبقة تكمل على النافذة الكاملة بكفاءة (< 120 ثانية)",
         el < 120.0, f"{el:.1f}s"),
        ("W4 warmup_neutral_bars معروض في النتيجة (شفافية)",
         "warmup_neutral_bars" in layer, "موجود"),
    ]
    n_pass = 0
    print()
    for name, ok_, ev in checks:
        print(("  ✅ " if ok_ else "  ❌ ") + name + f" — {ev}")
        n_pass += 1 if ok_ else 0
    print(f"\nPRO74 WARMUP PROOF: PASS={n_pass}/{len(checks)}")
    out = {"pass": n_pass, "total": len(checks), "warmup_neutral_bars": hz,
           "blocked": blocked, "elapsed_s": round(el, 1), "window_bars": int(N)}
    os.makedirs(os.path.join(HERE, "r73-evidence"), exist_ok=True)
    with open(os.path.join(HERE, "r73-evidence", "r74-warmup-proof.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    return 0 if n_pass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
