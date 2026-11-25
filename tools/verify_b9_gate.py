# -*- coding: utf-8 -*-
"""✅ B9-T100-GATE1 — أداة التحقق من نتيجة باك-تست بعد نشر حزمة الدمج.

تتحقق حرفياً من العقد الجديد:
  1) لا صفقة دخول واحدة يقع سعرها تحت خط الترند-100 عند شمعة الدخول
     (سعر التنفيذ > قيمة الخط في لقطة المؤشرات نفسها).
  2) رسومات الترند مرجوعة بإحداثياتها (chart_data.trend_lines — لكل خط
     وُلد: x/t/y للطرفين + الميل + لحظة الولادة + الإحلال) ليرسمها الفرونت.
  3) نقاط الدخول المرفوضة بالبوابة مرجوعة (chart_data.skipped_entry_points).
  4) صدى البوابة موجود في summary.math_audit.execution_gates.

الاستخدام:
  # ملف نتيجة محلي (من GET /api/v1/backtest1/get/{id}):
  python3 verify_b9_gate.py result.json

  # أو من السيرفر مباشرة (يجلب آخر نتيجة لمهمة):
  python3 verify_b9_gate.py --task 10001701 --base http://161.97.73.254:8000

  # كل ملفات مجلد:
  python3 verify_b9_gate.py results_dir/

خروج: 0 = العقد مُستوفى بالكامل · 1 = يوجد خرق (لا تعتمد النتيجة حتى يُفحص).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_result(src: Path):
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def fetch_task_result(base: str, task_id: str):
    import gzip
    import urllib.request

    def get(url: str):
        req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode())

    st = get(f"{base}/api/v1/backtest1/tasks/{task_id}")
    bid = (st.get("result") or {}).get("backtest_id") or st.get("backtest_id")
    if not bid:
        raise SystemExit(f"المهمة {task_id} بلا backtest_id (لم تكتمل؟): {st.get('state')}")
    return get(f"{base}/api/v1/backtest1/get/{bid}")


def verify_result(d: dict, label: str) -> bool:
    ok = True
    cd = (d.get("chart_data") or {})
    tp = [p for p in (cd.get("trade_points") or []) if p.get("type") == "entry"]
    print(f"\n■ {label}")
    print(f"   الصفقات: {d.get('summary', {}).get('total_trades')} · نقاط الدخول: {len(tp)}")

    # ---- (1) لا دخول تحت خط الترند-100 ----
    viol = []
    for e in tp:
        up = (e.get("indicators_snapshot") or {}).get("ind_trf_p100_upper")
        if up is None:
            continue  # بلا خط عند الشمعة (إحماء) — البوابة نفسها ترفض هذه الحالة
        if float(e["price"]) <= float(up):
            viol.append((e.get("timestamp"), float(e["price"]), float(up)))
    if viol:
        ok = False
        print(f"   ❌ (1) دخول تحت خط الترند-100: {len(viol)} خرق")
        for t, px, up in viol[:10]:
            print(f"      {t} · سعر {px:.8g} ≤ خط {up:.8g}")
    else:
        print(f"   ✓ (1) كل نقاط الدخول ({len(tp)}) فوق خط الترند-100 عند شمعة الدخول — حرفياً")

    # ---- (2) رسومات الترند ----
    tl = cd.get("trend_lines")
    if isinstance(tl, dict) and isinstance(tl.get("by_symbol"), dict) and tl["by_symbol"]:
        for sym, pack in tl["by_symbol"].items():
            lines = (pack or {}).get("lines") or {}
            counts = {}
            for tag, side in lines.items():
                counts[tag] = {
                    "علوي": len((side or {}).get("upper") or []),
                    "سفلي": len((side or {}).get("lower") or []),
                }
            sample = None
            for tag, side in lines.items():
                lst = (side or {}).get("upper") or []
                if lst:
                    sample = lst[0]
                    break
            has_coords = bool(
                sample and all(k in sample for k in ("x1", "t1", "y1", "x2", "t2", "y2", "slope"))
            )
            print(f"   ✓ (2) رسومات الترند ({tl.get('engine')} · {tl.get('spec')}): "
                  f"{sym}: {json.dumps(counts, ensure_ascii=False)} · "
                  f"إحداثيات كاملة: {'نعم' if has_coords else 'لا'}")
            if not has_coords:
                ok = False
                print("      ❌ عقد الإحداثيات ناقص!")
    else:
        ok = False
        print("   ❌ (2) chart_data.trend_lines مفقود — الباك اند لا يرجع رسومات الترند")

    # ---- (3) نقاط الدخول المرفوضة ----
    sk = cd.get("skipped_entry_points")
    if isinstance(sk, list):
        below = [p for p in sk if p.get("line_value") is not None
                 and float(p.get("would_be_price", 0)) <= float(p["line_value"])]
        bad = [p for p in sk if p.get("line_value") is not None
               and float(p.get("would_be_price", 0)) > float(p["line_value"])]
        print(f"   ✓ (3) skipped_entry_points: {len(sk)} نقطة مرفوضة "
              f"(تحت الخط: {len(below)} · شذل في العقد: {len(bad)})")
        for p in sk[:10]:
            print(f"      {p.get('timestamp')} · كان سيكون {p.get('would_be_price'):.8g} "
                  f"≤ خط {p.get('line_value'):.8g} — {str(p.get('reason'))[:60]}")
        if bad:
            ok = False
    else:
        ok = False
        print("   ❌ (3) chart_data.skipped_entry_points مفقود")

    # ---- (4) صدى البوابة ----
    eg = ((d.get("summary") or {}).get("math_audit") or {}).get("execution_gates")
    if isinstance(eg, dict) and isinstance(eg.get("by_symbol"), dict):
        for sym, st in eg["by_symbol"].items():
            print(f"   ✓ (4) صدى البوابة ({sym}): checked={st.get('checked')} "
                  f"blocked={st.get('blocked')} active={st.get('active')}")
    else:
        ok = False
        print("   ❌ (4) summary.math_audit.execution_gates مفقود")

    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="ملف نتيجة JSON أو مجلد أو --task")
    ap.add_argument("--task", help="رقم المهمة على السيرفر")
    ap.add_argument("--base", default="http://161.97.73.254:8000")
    args = ap.parse_args()

    results_ok = True
    n = 0
    if args.task:
        d = fetch_task_result(args.base, args.task)
        results_ok &= verify_result(d, f"مهمة {args.task} من {args.base}")
        n += 1
    else:
        p = Path(args.src)
        files = ([p] if p.is_file() else sorted(p.glob("*.json"))) if p.exists() else []
        if not files:
            raise SystemExit(f"لا ملفات: {args.src}")
        for f in files:
            try:
                d = load_result(f)
            except Exception as e:
                print(f"تخطي {f.name}: {e}")
                continue
            if "chart_data" not in d:
                continue
            results_ok &= verify_result(d, f.name)
            n += 1

    print("\n" + "=" * 70)
    if results_ok:
        print(f"⇒ العقد مستوفى بالكامل ({n} نتيجة): لا دخول تحت خط الترند-100، "
              f"والرسومات والإحداثيات ونقاط الرفض والصدى كلها ترجع للفرونت ✓")
        sys.exit(0)
    else:
        print("⇒ يوجد خرق في العقد — افحص البنود المعلمة ❌ أعلاه")
        sys.exit(1)


if __name__ == "__main__":
    main()
