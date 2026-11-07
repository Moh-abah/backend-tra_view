#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_round39_contract.py — البرهان الحتمي لعقد الجولة 39 (رد وكيل الباك-اند
على تقرير وكيل الفرونت ج38).

الفكرة: ج39 = ج34 + 4 إضافات صرفة فقط (pivots · window · display · is_launch).
البرهان يُنفَّذ على اللقطة الذهبية (2000 شمعة BTC 1m — بلا شبكة إطلاقاً):

  البرهان A (الإضافات فقط):
    بعد حذف المفاتيح الأربعة الجديدة — ومواقعها الحصرية فقط — من حمولة ج39
    يجب أن تتطابق الحمولة المتبقية مع حمولة ج34 **تطابقاً كاملاً** (deep-equal).
    هذا يثبت رياضياً: لا إزالة، لا إعادة تسمية، لا تغيير قيمة واحدة.

  البرهان B (صحة الإضافات):
    B1  pivots[]: عددها = legs+1 · تسلسل الأطراف متشارك
        (pivots[k+1] ≡ legs[k].x2 و pivots[k+1].bar == legs[k+1].x1)
        · kind من الساق · الأنواع متناوبة top/bottom · الأزمنة غير صفرية
        ومطابقة لأزمنة الساقات · confirmed_at_bar ≥ bar.
    B2  display == round(1 − ratio, 5) (اصطلاح TV — عقد ROUND18:
        engine(L) ≡ frontend(1−L)).
    B3  is_launch: علم واحد بالضبط لكل نطاق غير منحل عند المستوى الذي
        قيمته == launch_line حرفياً (نفس معادلة المستويات) · المنحل بلا علم.
    B4  window: {bars, time_from, time_to} == هوية اللقطة الذهبية نفسها.

الاستخدام:
    python3 verify_round39_contract.py --baseline <V34_PROJECT_ROOT> \
        --candidate <V39_PROJECT_ROOT> --golden <golden_btc_1m.json> \
        [--outdir evidence_out]

الافتراضي (تشغيل من جذر الحزمة):
    baseline  = verify_scripts/baseline_r34        (نسخة ج34 كما شُحنت)
    candidate = جذر الحزمة نفسه                     (ملفات ج39)

⚠️ المساران "جذر مشروع" — أي المجلد الذي يحتوي app/ بداخله (وليس app/ نفسها).
   لخادمك: --candidate /path/to/your/project
"""
import argparse
import copy
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

NEW_TOP_KEYS = ("pivots", "window")
NEW_LEVEL_KEYS = ("display", "is_launch")
LAUNCH_ENGINE_LEVEL = 0.382  # عقد المحرك: خط الانطلاقة = price(0.382) بمقياس المحرك

RESULTS = {"passed": 0, "failed": 0, "checks": []}


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    if ok:
        RESULTS["passed"] += 1
        print(f"  ✓ {name}" + (f" — {detail}" if detail else ""))
    else:
        RESULTS["failed"] += 1
        print(f"  ✗ FAIL: {name}" + (f" — {detail}" if detail else ""))
    return ok


def gen_payload(app_root: str, out_path: str, golden: str) -> None:
    cmd = [sys.executable, os.path.join(HERE, "gen_payload.py"),
           os.path.abspath(app_root), os.path.abspath(out_path), os.path.abspath(golden)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise RuntimeError(f"gen_payload failed for {app_root}")


# ---------------------------------------------------------------------------
# البرهان A — الإضافات فقط (حذف المواقع الحصرية للجديد يجب أن يعيد ج34 حرفياً)
# ---------------------------------------------------------------------------
def strip_new_keys(p39: dict) -> dict:
    p = copy.deepcopy(p39)
    p.pop("pivots", None)
    p.pop("window", None)
    for rng in p.get("ranges") or []:
        for lv in rng.get("levels") or []:
            for k in NEW_LEVEL_KEYS:
                lv.pop(k, None)
    cur = p.get("current") or {}
    for lv in cur.get("levels") or []:
        for k in NEW_LEVEL_KEYS:
            lv.pop(k, None)
    return p


def proof_additions_only(tag: str, p34: dict, p39: dict) -> None:
    print(f"\n[البرهان A — {tag}: الإضافات فقط]")
    for k in NEW_TOP_KEYS:
        check(f"{tag}: المفتاح {k} غائب في ج34", k not in p34)
    lv34 = (p34.get("ranges") or [{}])[0].get("levels", [{}])[0] if p34.get("ranges") else {}
    for k in NEW_LEVEL_KEYS:
        check(f"{tag}: حقل المستوى {k} غائب في ج34", k not in lv34)
    check(f"{tag}: المفتاحان موجودان في ج39", "pivots" in p39 and "window" in p39)
    stripped = strip_new_keys(p39)
    check(f"{tag}: ج39 − (المفاتيح الجديدة بمواقعها الحصرية) == ج34 حرفياً",
          stripped == p34,
          "تطابق كامل بعد الحذف (deep-equal) — لا إزالة/إعادة تسمية/تغيير قيمة واحدة")
    if stripped != p34:
        # تشخيص أول اختلاف
        for k in sorted(set(stripped) | set(p34)):
            if stripped.get(k) != p34.get(k):
                check(f"{tag}: أول مفتاح مختلف", False, k)
                break


# ---------------------------------------------------------------------------
# البرهان B — صحة الإضافات
# ---------------------------------------------------------------------------
def proof_pivots(tag: str, p39: dict, candles: list) -> None:
    print(f"\n[البرهان B1 — {tag}: pivots من النواة]")
    piv, legs = p39.get("pivots") or [], p39.get("legs") or []
    check(f"{tag}: len(pivots) == len(legs)+1", len(piv) == len(legs) + 1,
          f"{len(piv)} محوراً / {len(legs)} ساقاً")
    if not piv or not legs:
        return
    ok_start = (piv[0]["bar"] == legs[0]["x1"] and piv[0]["price"] == legs[0]["y1"])
    check(f"{tag}: المحور الأول = بداية أول ساق", ok_start)
    ok_chain = ok_time = ok_kind = ok_conf = True
    for k, lg in enumerate(legs):
        pv = piv[k + 1]
        if not (pv["bar"] == lg["x2"] and pv["price"] == lg["y2"]):
            ok_chain = False
        if pv["time"] != lg["t2"]:
            ok_time = False
        if pv["kind"] != lg["kind"]:
            ok_kind = False
        if pv["confirmed_at_bar"] < pv["bar"]:
            ok_conf = False
    check(f"{tag}: كل محور k+1 = طرف الساق k (سلسلة متشاركة)", ok_chain)
    check(f"{tag}: أزمنة المحاور == أزمنة أطراف الساقات", ok_time)
    check(f"{tag}: kind المحور = kind ساقته", ok_kind)
    check(f"{tag}: confirmed_at_bar ≥ bar لكل محور", ok_conf)
    ok_alt = all(a["kind"] != b["kind"] for a, b in zip(piv, piv[1:]))
    check(f"{tag}: الأنواع متناوبة top/bottom", ok_alt)
    ok_live = all(p["time"] and p["time"] > 0 for p in piv)
    check(f"{tag}: كل الأزمنة epoch-ms غير صفرية (إصلاح ج34 قائم)", ok_live)
    ok_mt = all(piv[k]["bar"] < piv[k + 1]["bar"] for k in range(len(piv) - 1))
    check(f"{tag}: الأشرطة تصاعدية بلا تكرار", ok_mt)


def proof_levels(tag: str, p39: dict) -> None:
    print(f"\n[البرهان B2+B3 — {tag}: display و is_launch]")
    rngs = p39.get("ranges") or []
    n_lv = sum(len(r.get("levels") or []) for r in rngs)
    ok_disp = True
    for r in rngs:
        for lv in r.get("levels") or []:
            if lv.get("display") != round(1.0 - lv["ratio"], 5):
                ok_disp = False
    check(f"{tag}: display == round(1−ratio,5) لكل المستويات ({n_lv})", ok_disp)
    ok_one, ok_val, ok_ratio, ok_degen = True, True, True, True
    n_launch = 0
    for r in rngs:
        flagged = [lv for lv in (r.get("levels") or []) if lv.get("is_launch")]
        n_launch += len(flagged)
        if r.get("degenerate"):
            if flagged:
                ok_degen = False
            continue
        if len(flagged) != 1:
            ok_one = False
            continue
        if abs(flagged[0]["value"] - r["launch_line"]) > 1e-9:
            ok_val = False
        if abs(flagged[0]["ratio"] - LAUNCH_ENGINE_LEVEL) > 1e-12:
            ok_ratio = False
    check(f"{tag}: علم واحد بالضبط لكل نطاق غير منحل ({n_launch}/{len(rngs)})", ok_one)
    check(f"{tag}: قيمة المستوى المعلَّم == launch_line حرفياً", ok_val)
    check(f"{tag}: المستوى المعلَّم = 0.382 بمقياس المحرك", ok_ratio)
    check(f"{tag}: النطاقات المنحلة بلا علم", ok_degen)
    cur = p39.get("current") or {}
    if cur:
        clv = cur.get("levels") or []
        ok_cd = all(lv.get("display") == round(1.0 - lv["ratio"], 5) for lv in clv)
        flagged = [lv for lv in clv if lv.get("is_launch")]
        ok_cl = (len(flagged) == 1 and abs(flagged[0]["value"] - cur["launch_line"]) < 1e-9)
        check(f"{tag}: current.levels تحمل display/is_launch كذلك", ok_cd and ok_cl,
              f"{len(clv)} مستويات")


def proof_window(tag: str, p39: dict, candles: list) -> None:
    print(f"\n[البرهان B4 — {tag}: window]")
    w = p39.get("window") or {}
    t0 = int(candles[0]["time"])
    tN = int(candles[-1]["time"])
    check(f"{tag}: window.bars == عدد الشموع", w.get("bars") == len(candles),
          f"{w.get('bars')} == {len(candles)}")
    check(f"{tag}: window.time_from == أول شمعة", w.get("time_from") == t0)
    check(f"{tag}: window.time_to == آخر شمعة", w.get("time_to") == tN)


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=os.path.join(HERE, "baseline_r34"))
    ap.add_argument("--candidate", default=os.path.abspath(os.path.join(HERE, "..")))
    ap.add_argument("--golden", default=os.path.join(HERE, "golden_btc_1m.json"))
    ap.add_argument("--outdir", default=os.path.join(HERE, "evidence"))
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    t0 = time.time()
    print("=" * 74)
    print("برهان عقد الجولة 39 — رد وكيل الباك-اند على تقرير وكيل الفرونت ج38")
    print(f"  baseline (ج34):  {args.baseline}")
    print(f"  candidate (ج39): {args.candidate}")
    print(f"  golden: {args.golden} (بلا شبكة — حتمي)")
    print("=" * 74)

    p34_path = os.path.join(args.outdir, "payload_r34.json")
    p39_path = os.path.join(args.outdir, "payload_r39.json")
    gen_payload(args.baseline, p34_path, args.golden)
    gen_payload(args.candidate, p39_path, args.golden)

    p34s = json.load(open(p34_path, encoding="utf-8"))
    p39s = json.load(open(p39_path, encoding="utf-8"))
    candles = json.load(open(args.golden, encoding="utf-8"))

    for strat in ("zzfib_e2e", "zzfib_e2e_trendy"):
        print("\n" + "—" * 74)
        print(f"الاستراتيجية: {strat}")
        print("—" * 74)
        p34, p39 = p34s[strat], p39s[strat]
        proof_additions_only(strat, p34, p39)
        proof_pivots(strat, p39, candles)
        proof_levels(strat, p39)
        proof_window(strat, p39, candles)

    # برهان إضافي: توحيد الاستراتيجيتين (نفس النواة => نفس المحاور والساقات)
    print("\n[البرهان C — النواة الموحدة: نفس المحاور في الاستراتيجيتين]")
    e2e, tr = p39s["zzfib_e2e"], p39s["zzfib_e2e_trendy"]
    check("نفس عدد المحاور بين e2e والترندية",
          len(e2e.get("pivots") or []) == len(tr.get("pivots") or []),
          f"{len(e2e.get('pivots') or [])} == {len(tr.get('pivots') or [])}")
    same = all(a == b for a, b in zip(e2e.get("pivots") or [], tr.get("pivots") or []))
    check("المحاور متطابقة قيمةً-بقيمة (زقزاق واحد موحد)", same)

    dur = round(time.time() - t0, 1)
    total = RESULTS["passed"] + RESULTS["failed"]
    print("\n" + "=" * 74)
    print(f"النتيجة: {RESULTS['passed']}/{total} فحصاً ناجحاً · {RESULTS['failed']} إخفاق · {dur}ث")
    print("=" * 74)

    ev = {
        "round": 39,
        "proof": "additions-only contract completion (reply to frontend R38)",
        "golden": {"candles": len(candles), "time_from": candles[0]["time"],
                   "time_to": candles[-1]["time"]},
        "summary": {
            "e2e": {"legs": len(e2e.get("legs") or []),
                    "pivots": len(e2e.get("pivots") or []),
                    "ranges": len(e2e.get("ranges") or []),
                    "levels_total": sum(len(r.get("levels") or []) for r in e2e.get("ranges") or [])},
            "trendy": {"legs": len(tr.get("legs") or []),
                       "pivots": len(tr.get("pivots") or []),
                       "ranges": len(tr.get("ranges") or []),
                       "levels_total": sum(len(r.get("levels") or []) for r in tr.get("ranges") or [])},
        },
        "passed": RESULTS["passed"],
        "failed": RESULTS["failed"],
        "duration_sec": dur,
        "checks": RESULTS["checks"],
    }
    ev_path = os.path.join(args.outdir, "round39_contract_verification.json")
    with open(ev_path, "w", encoding="utf-8") as f:
        json.dump(ev, f, ensure_ascii=False, indent=1)
    print(f"حُفظ الدليل: {ev_path}")
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
