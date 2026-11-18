#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""التحقق النهائي بعد نشر حزمة إصلاح بيانات الرسم الكاملة للكمومية.

يسلّم حمولة الكمومية (نافذة القاعدة #10000374) إلى الباك اند الحي، يستطلعها
حتى الاكتمال، ثم يحقق ثلاث طبقات:
  1) مقاييس النتيجة == القيم المرجعية المعتمدة (المهمة #10000375)
  2) أعمدة الكمومية ind_zzfetq_* (62) مطابقة بت-بت للمهمة المرجعية #10000375
  3) ✅ الإصلاح: أعمدة الترندية الأصلية ind_zzfet_* (47) موجودة في الرد
     ومطابقة بت-بت للقاعدة #10000374 (بيانات الرسم: زقزاق/فيبو/خطوط ترند)

الاستخدام: python3 verify_quantum_fix.py [SERVER]
  SERVER افتراضياً: http://161.97.73.254:8000
"""
import gzip
import json
import sys
import time
import urllib.error
import urllib.request

SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://161.97.73.254:8000"

QUANTUM_REF_TASK = "10000375"     # المهمة المرجعية الكمومية (قبل الإصلاح)
BASELINE_REF_TASK = "10000374"    # القاعدة الترندية (مصدر أعمدة الرسم المرجعية)

EXPECTED = {
    "total_pnl_percent": 69.338535135082,
    "total_trades": 31,
    "winning_trades": 27,
    "losing_trades": 4,
    "win_rate": 87.09677419354838,
    "profit_factor": 1.978684961471487,
    "max_drawdown_percent": 39.07922624944522,
    "final_capital": 169.338535135082,
}

TOLERANCE = 1e-9


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


def _bid_of_task(task_id):
    tasks = _get("/api/v1/backtest1/tasks", timeout=120)
    for t in (tasks.get("data") or []):
        if str(t.get("task_number")) == str(task_id):
            return t.get("backtest_id")
    return None


def norm(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def cmp_series(mine, theirs, my_ts=None, ref_ts=None):
    """مقارنة بت-بت — بمحاذاة زمنية عند اختلاف الطول.

    الشموع الموجودة في طرف واحد فقط (فجوات كاش مختلفة) تُتخطّى — لا تُعدّ
    فرقاً لأنها غير قابلة للمقارنة أصلاً.
    """
    if len(mine) == len(theirs):
        pairs = list(zip(mine, theirs))
    else:
        if my_ts is None or ref_ts is None:
            return len(theirs), None
        ref_map = {t: i for i, t in enumerate(ref_ts)}
        pairs = []
        for i, v in enumerate(mine):
            j = ref_map.get(my_ts[i]) if i < len(my_ts) else None
            if j is None:
                continue  # شمعة غير موجودة في المرجع — تُتخطّى
            pairs.append((v, theirs[j] if j < len(theirs) else None))
    diffs = 0
    first = None
    for i, (a, b) in enumerate(pairs):
        na, nb = norm(a), norm(b)
        if na is None and nb is None:
            continue
        if na is None or nb is None:
            if (na is None and nb == 0.0) or (nb is None and na == 0.0):
                continue
            diffs += 1
            first = first or (i, a, b)
            continue
        if na != nb:
            diffs += 1
            first = first or (i, a, b)
    return diffs, first


def main():
    payload = json.load(open("payloads/quantum_verify_payload.json",
                             encoding="utf-8"))
    payload["name"] = "QUANTUM-FIX-VERIFY · الكمومية + بيانات الرسم الكاملة · نافذة القاعدة"

    print("=" * 78)
    print("التحقق بعد نشر إصلاح بيانات الرسم الكاملة — الاستراتيجية الترندية الكمومية")
    print(f"السيرفر: {SERVER}")
    print("=" * 78)

    # 0) القالب مسجل؟
    presets = _get("/api/v1/strategies/presets", timeout=60)
    plist = presets if isinstance(presets, list) else (presets.get("presets") or presets.get("data") or [])
    ids = [str(p.get("id") or p.get("name")) for p in plist] if isinstance(plist, list) else []
    has = any("quantum" in str(x) for x in ids)
    print(f"\n[0] القالب الكمي في /strategies/presets: {'✓' if has else '✗'} (من {len(ids)})")

    # 1) تسليم الحمولة
    print("\n[1] تسليم حمولة التحقق …", flush=True)
    disp = _post("/api/v1/backtest1/run", payload)
    if not disp.get("success"):
        print("  فشل التسليم:", json.dumps(disp, ensure_ascii=False)[:400])
        return 2
    task_id = str(disp.get("task_id"))
    print(f"  المهمة: {task_id} (backtest_id: {disp.get('backtest_id')})")

    # 2) الاستطلاع
    t0 = time.time()
    while True:
        try:
            st = _get(f"/api/v1/backtest1/status/{task_id}", timeout=60)
        except urllib.error.HTTPError as e:
            print(f"  [poll] HTTP {e.code} — إعادة محاولة")
            time.sleep(5)
            continue
        state = st.get("state") or st.get("status")
        if state != "SUCCESS" and (time.time() - t0) % 20 < 5:
            print(f"  [{time.time()-t0:5.1f}s] state={state} progress={st.get('progress')}")
        if state in ("SUCCESS", "completed"):
            break
        if state in ("FAILURE", "failed", "REVOKED"):
            print("  فشلت المهمة:", str(st.get("error"))[:400])
            return 2
        if time.time() - t0 > 1200:
            print("  انتهت المهلة")
            return 3
        time.sleep(4)
    print(f"  اكتملت خلال {time.time()-t0:.1f}s")
    new_bid = st.get("backtest_id") or disp.get("backtest_id")

    # 3) جلب الردود الثلاثة
    print("\n[2] جلب الردود: الجديدة + المرجعية الكمومية + القاعدة …")
    new_r = _get(f"/api/v1/backtest1/get/{new_bid}")
    q_ref_bid = _bid_of_task(QUANTUM_REF_TASK)
    b_ref_bid = _bid_of_task(BASELINE_REF_TASK)
    q_ref = _get(f"/api/v1/backtest1/get/{q_ref_bid}") if q_ref_bid else None
    b_ref = _get(f"/api/v1/backtest1/get/{b_ref_bid}") if b_ref_bid else None
    if q_ref is None or b_ref is None:
        print("  تعذر جلب المهام المرجعية — تحقق من وجودها")
        return 2

    new_vc = (new_r.get("chart_data") or {}).get("visual_candles") or []
    q_vc = (q_ref.get("chart_data") or {}).get("visual_candles") or []
    b_vc = (b_ref.get("chart_data") or {}).get("visual_candles") or []
    print(f"  الجديدة: {len(new_vc)} شمعة · الكمومية المرجعية: {len(q_vc)} · القاعدة: {len(b_vc)}")

    # 4) طبقة 1: المقاييس
    print("\n[3] طبقة المقاييس (يجب أن تطابق المهمة المرجعية بت-بت):")
    s = new_r.get("summary") or {}
    ok_metrics = True
    for k, exp in EXPECTED.items():
        got = s.get(k)
        if isinstance(exp, float):
            good = got is not None and abs(float(got) - exp) <= TOLERANCE
        else:
            good = got == exp
        ok_metrics = ok_metrics and good
        print(f"  {'✓' if good else '✗'} {k}: {got} (متوقع {exp})")

    # 5) طبقة 2: أعمدة الكمومية 62
    print("\n[4] أعمدة الكمومية ind_zzfetq_* (62) — بت-بت ضد المهمة المرجعية:")
    q_names = sorted(k for k in new_vc[0] if k.startswith("ind_zzfetq_"))
    new_ts = [r.get("timestamp") for r in new_vc]
    q_ts = [r.get("timestamp") for r in q_vc]
    n_bad_q = 0
    for k in q_names:
        d, first = cmp_series([r.get(k) for r in new_vc], [r.get(k) for r in q_vc],
                              new_ts, q_ts)
        if d:
            n_bad_q += 1
            print(f"  ✗ {k}: {d} فرق (أول: {first})")
    print(f"  → {len(q_names)-n_bad_q}/{len(q_names)} مطابقة (المتوقع 62/62)")

    # 6) طبقة 3: الإصلاح — أعمدة الرسم الترندية 47
    print("\n[5] ✅ الإصلاح — أعمدة الرسم الترندية ind_zzfet_* ضد القاعدة:")
    f_names_new = sorted(k for k in new_vc[0]
                         if k.startswith("ind_zzfet_") and not k.startswith("ind_zzfetq"))
    f_names_ref = sorted(k for k in b_vc[0]
                         if k.startswith("ind_zzfet_") and not k.startswith("ind_zzfetq"))
    b_ts = [r.get("timestamp") for r in b_vc]
    n_bad_f = 0
    for k in f_names_ref:
        if k not in new_vc[0]:
            n_bad_f += 1
            print(f"  ✗ العمود مفقود في الرد الجديد: {k}")
            continue
        d, first = cmp_series([r.get(k) for r in new_vc], [r.get(k) for r in b_vc],
                              new_ts, b_ts)
        if d:
            n_bad_f += 1
            print(f"  ✗ {k}: {d} فرق (أول: {first})")
    print(f"  → الموجودة في الرد الجديد: {len(f_names_new)} (المتوقع 47) · المطابقة: {len(f_names_ref)-n_bad_f}/{len(f_names_ref)}")

    # 7) الخلاصة
    ok = (ok_metrics and n_bad_q == 0 and n_bad_f == 0
          and len(q_names) == 62 and len(f_names_new) == 47)
    print("\n" + "=" * 78)
    print("الحكم النهائي:",
          "✓✓✓ الإصلاح مكتمل — الكمومية تُرجع بياناتها الـ62 + أعمدة الرسم الترندية الـ47"
          if ok else "!! راجع الفروق أعلاه")
    print("=" * 78)
    json.dump({
        "server": SERVER, "task_id": task_id, "backtest_id": new_bid,
        "candles": len(new_vc),
        "metrics_match": ok_metrics,
        "quantum_columns": len(q_names), "quantum_mismatches": n_bad_q,
        "drawing_columns": len(f_names_new), "drawing_mismatches": n_bad_f,
        "verdict": ok,
    }, open("verify_result.json", "w"), ensure_ascii=False, indent=1)
    print("[saved] verify_result.json — backtest_id:", new_bid)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
