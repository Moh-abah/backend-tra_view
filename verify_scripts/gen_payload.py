#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_payload.py — مولّد حمولات العقد لعزل المقارنة (ج39).

الاستخدام:
    python3 gen_payload.py <APP_ROOT> <OUT_JSON> <GOLDEN_JSON>

يشغّل zzfib_e2e و zzfib_e2e_trendy على اللقطة الذهبية من APP_ROOT
(جذر شجرة app/ المعزولة) ويحفظ الحمولتين JSON للفحص.

⚠️ يشغَّل في عملية مستقلة لكل جذر — عزل تام لاستيراد الوحدات
(نفس اسم الوحدة app.services.indicators.* في الجذرين).
"""
import json
import sys


def main() -> int:
    app_root, out_path, golden_path = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.path.insert(0, app_root)

    from app.services.indicators.overlays_zlf_e2e import zigzag_fib_e2e
    from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy

    candles = json.load(open(golden_path, encoding="utf-8"))
    payload = {
        "zzfib_e2e": zigzag_fib_e2e(candles),
        "zzfib_e2e_trendy": zigzag_fib_e2e_trendy(candles),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"[gen_payload] {app_root} -> {out_path} "
          f"(e2e legs={len(payload['zzfib_e2e']['legs'])}, "
          f"trendy legs={len(payload['zzfib_e2e_trendy']['legs'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
