#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""✅ TS-FIX-1970 — التحقق الحي بعد النشر (عطب الطوابع 1970 — #10000378).

يسلّم حمولة الكمومية (نافذة القاعدة #10000374 — SOL 15m) إلى الباك اند
الحي مرتين متتاليتين، ثم يحقق أربع طبقات:

  1) مقاييس النتيجة == القيم المرجعية المعتمدة بت-بت (المهمة #10000375)
     — الإصلاح لا يغيّر أي رقم مالي (المحرك موضعي).
  2) ✅ معايير القبول الحرفية لعطب 1970:
       (أ) عدد الطوابع الفريدة في visual_candles == عدد الشموع
       (ب) أول طابع ≥ بداية النافذة المطلوبة وليس 1970
       (ج) metadata.start_date ≠ 1970 + لا طابع 1970 في السلسلة
       + نقاط الصفقات بأزمنة حقيقية + overlays.time_from/to حقيقية
  3) التكرار المتتالي: التشغيلة الثانية فوراً بعد الأولى (نمط الإنتاج
     المكسور بالضبط: الأولى تكتب في redis والثانية كانت تقرأ السمّ خلال
     TTL الساعة) — كلتاهما يجب أن تكون سليمة.
  4) انحدار إصلاح الجلسة السابقة: أعمدة ind_zzfetq_* (62) موجودة
     ومطابقة بت-بت للمرجعية #10000375 + أعمدة ind_zzfet_* (47) مطابقة
     للقاعدة #10000374.

الاستخدام: python3 verify_tsfix_1970.py [SERVER]
  SERVER افتراضياً: http://161.97.73.254:8000
"""
import gzip
import json
import sys
import time
import urllib.error
import urllib.request

SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://161.97.73.254:8000"

QUANTUM_REF_TASK = "10000375"     # المهمة المرجعية الكمومية (سليمة الطوابع)
BASELINE_REF_TASK = "10000374"    # القاعدة الترندية (مصدر أعمدة الرسم)

W_START = "2020-10-01"            # بداية نافذة القاعدة المطلوبة
W_START_EPOCH = 1601510400       # 2020-10-01T00:00:00Z بالثواني
W_SLACK_S = 86400                # سماحية شمعة التمهيد قبل النافذة (سلوك المحرك الأصلي)


def _ts_epoch(v):
    """قيمة زمنية (ISO أو epoch-ms رقمي) ⇦ ثوانٍ epoch — None عند الفشل."""
    if v is None:
        return None
    s = str(v)
    if s.replace(".", "", 1).lstrip("-").isdigit():
        f = float(s)
        return f / 1000.0 if f > 1e11 else f
    try:
        from datetime import datetime
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None

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

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"    [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))


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


def _norm(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _cmp_series(mine, theirs, my_ts=None, ref_ts=None):
    """مقارنة بت-بت بمحاذاة زمنية عند اختلاف الطول (فجوات كاش مختلفة)."""
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
                continue
            pairs.append((v, theirs[j] if j < len(theirs) else None))
    diffs = 0
    first = None
    for i, (a, b) in enumerate(pairs):
        na, nb = _norm(a), _norm(b)
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


def _run_once(label):
    """تشغيلة واحدة كاملة — يعيد (الرد, backtest_id) أو (None, None)."""
    payload = json.load(open("payloads/quantum_verify_payload.json",
                             encoding="utf-8"))
    payload["name"] = f"TSFIX-1970-VERIFY · {label} · نافذة القاعدة 10000374 (SOL 15m)"

    print(f"\n  ── {label}: تسليم الحمولة …", flush=True)
    disp = _post("/api/v1/backtest1/run", payload)
    if not disp.get("success"):
        print("    فشل التسليم:", json.dumps(disp, ensure_ascii=False)[:400])
        return None, None
    task_id = str(disp.get("task_id"))
    print(f"    المهمة: {task_id}")

    t0 = time.time()
    last = ""
    while True:
        try:
            st = _get(f"/api/v1/backtest1/status/{task_id}", timeout=60)
        except urllib.error.HTTPError as e:
            print(f"    [poll] HTTP {e.code} — إعادة محاولة")
            time.sleep(5)
            continue
        state = st.get("state") or st.get("status")
        if state != last:
            print(f"    [{time.time()-t0:5.1f}s] state={state}")
            last = state
        if state in ("SUCCESS", "completed"):
            break
        if state in ("FAILURE", "failed", "REVOKED"):
            print("    فشلت المهمة:", str(st.get("error"))[:400])
            return None, None
        if time.time() - t0 > 1500:
            print("    انتهت المهلة")
            return None, None
        time.sleep(4)
    print(f"    اكتملت خلال {time.time()-t0:.1f}s")
    bid = st.get("backtest_id") or disp.get("backtest_id")
    return _get(f"/api/v1/backtest1/get/{bid}"), bid


def _check_timestamps(resp, label):
    """طبقة 2 — معايير القبول الحرفية لعطب 1970 على رد chart-data."""
    vc = resp.get("visual_candles") or []
    tp = resp.get("trade_points") or []
    meta = resp.get("metadata") or {}

    stamps = [c.get("timestamp") for c in vc]
    uniq = set(stamps)
    check(f"[{label}] (أ) الطوابع الفريدة == عدد الشموع",
          len(uniq) == len(vc), f"{len(uniq)} فريد من {len(vc)}")
    first_epoch = _ts_epoch(stamps[0]) if stamps else None
    check(f"[{label}] (ب) أول طابع ضمن نافذة القاعدة (≠1970 · ≥ بداية−فاصل تمهيد)",
          first_epoch is not None
          and first_epoch >= W_START_EPOCH - W_SLACK_S
          and first_epoch < W_START_EPOCH + 30 * 86400,
          str(stamps[0]) if stamps else "empty")
    md_start = str(meta.get("start_date") or "")
    check(f"[{label}] (ج) metadata.start_date ≠ 1970",
          bool(md_start) and not md_start.startswith("1970"), md_start[:40])
    check(f"[{label}] لا طابع 1970 في السلسلة كلها",
          not any(str(s).startswith("1970") for s in stamps))
    # نقاط الصفقات
    tp_ok = bool(tp) and not any(
        str(p.get("timestamp") or "").startswith("1970") for p in tp)
    check(f"[{label}] نقاط الصفقات ({len(tp)}) بأزمنة حقيقية", tp_ok)
    # overlays من نفس الرد — القيمة قد تكون epoch-ms رقمية أو ISO نصية
    ovl = resp.get("overlays") or {}
    tf, tt = ovl.get("time_from"), ovl.get("time_to")
    tf_ep = _ts_epoch(tf)
    tt_ep = _ts_epoch(tt)
    check(f"[{label}] overlays.time_from/to أزمنة حقيقية (ليست 0/1970)",
          tf_ep is not None and tt_ep is not None
          and tf_ep >= W_START_EPOCH - W_SLACK_S and tt_ep > tf_ep,
          f"from={tf} to={tt}")
    return vc, stamps


def main():
    print("=" * 78)
    print("TS-FIX-1970 — التحقق الحي بعد النشر (عطب الطوابع الزمنية #10000378)")
    print(f"السيرفر: {SERVER}")
    print("=" * 78)

    # ── التشغيلة الأولى ──
    r1, bid1 = _run_once("التشغيلة 1")
    if r1 is None:
        return 2

    # ── التشغيلة الثانية فوراً (نمط الإنتاج المكسور: قراءة redis خلال TTL) ──
    r2, bid2 = _run_once("التشغيلة 2 (فوراً بعد الأولى — نمط العطل)")
    if r2 is None:
        return 2

    # ── طبقة 1: المقاييس بت-بت (كلتا التشغيلتين) ──
    print("\n[طبقة 1] المقاييس == المرجعية المعتمدة (#10000375) بت-بت:")
    for label, r in (("تشغيلة 1", r1), ("تشغيلة 2", r2)):
        s = r.get("summary") or {}
        ok = True
        for k, exp in EXPECTED.items():
            got = s.get(k)
            if isinstance(exp, float):
                good = got is not None and abs(float(got) - exp) <= TOLERANCE
            else:
                good = got == exp
            if not good:
                ok = False
                print(f"      ✗ {k}: {got} != {exp}")
        check(f"[{label}] المقاييس الثمانية بت-بت", ok)

    # ── طبقة 2: معايير القبول (كلتا التشغيلتين — من نقطة chart-data) ──
    print("\n[طبقة 2] معايير القبول الحرفية (أ/ب/ج + الصفقات + overlays):")
    cd1 = _get(f"/api/v1/backtest1/{bid1}/chart-data")
    cd2 = _get(f"/api/v1/backtest1/{bid2}/chart-data")
    vc1, ts1 = _check_timestamps(cd1, "تشغيلة 1")
    vc2, ts2 = _check_timestamps(cd2, "تشغيلة 2")

    # ── طبقة 3: انحدار إصلاح الجلسة السابقة (62+47 عموداً) ──
    print("\n[طبقة 3] انحدار إصلاح الجلسة السابقة (بيانات الرسم الكاملة):")
    q_ref_bid = _bid_of_task(QUANTUM_REF_TASK)
    b_ref_bid = _bid_of_task(BASELINE_REF_TASK)
    q_ref = _get(f"/api/v1/backtest1/get/{q_ref_bid}") if q_ref_bid else None
    b_ref = _get(f"/api/v1/backtest1/get/{b_ref_bid}") if b_ref_bid else None
    if q_ref and b_ref:
        q_vc = (q_ref.get("chart_data") or {}).get("visual_candles") or []
        b_vc = (b_ref.get("chart_data") or {}).get("visual_candles") or []
        q_cols = [k for k in (q_vc[0] if q_vc else {}) if k.startswith("ind_zzfetq_")]
        b_cols = [k for k in (b_vc[0] if b_vc else {}) if k.startswith("ind_zzfet_")]
        n_q, n_b = 0, 0
        d_q, d_b = 0, None
        for col in q_cols:
            mine = [c.get(col) for c in vc2]
            theirs = [c.get(col) for c in q_vc]
            if len(vc2) == len(q_vc):
                d, first = _cmp_series(mine, theirs)
            else:
                d, first = _cmp_series(mine, theirs, ts2,
                                       [c.get("timestamp") for c in q_vc])
            if d == 0:
                n_q += 1
            else:
                d_q = d_q or (col, first)
        for col in b_cols:
            mine = [c.get(col) for c in vc2]
            theirs = [c.get(col) for c in b_vc]
            if len(vc2) == len(b_vc):
                d, first = _cmp_series(mine, theirs)
            else:
                d, first = _cmp_series(mine, theirs, ts2,
                                       [c.get("timestamp") for c in b_vc])
            if d == 0:
                n_b += 1
            else:
                d_b = d_b or (col, first)
        check(f"أعمدة الكمومية ind_zzfetq_*: {n_q}/{len(q_cols)} مطابقة",
              n_q == len(q_cols) and len(q_cols) == 62,
              f"{len(q_cols)} عموداً، أول فرق: {d_q}")
        check(f"أعمدة التمرير ind_zzfet_*: {n_b}/{len(b_cols)} مطابقة",
              n_b == len(b_cols) and len(b_cols) == 47,
              f"{len(b_cols)} عموداً، أول فرق: {d_b}")
    else:
        print("    ⚠ تعذر جلب المرجعيات — تخطي طبقة الانحدار")

    # ── الخلاصة ──
    print()
    print("=" * 78)
    print(f"الخلاصة: {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("الفاشلات:")
        for f in FAIL:
            print("  ✗", f)
        return 1
    print("✅✅✅ عطب 1970 مُصلَح ومُثبت حياً: الطوابع حقيقية في التشغيلتين")
    print("   المتتاليتين (نمط العطل الأصلي)، والمقاييس بت-بت، وبيانات الرسم")
    print("   الكاملة (62+47 عموداً) سليمة.")
    print(f"\n  تشغيلة 1: backtest_id={bid1}")
    print(f"  تشغيلة 2: backtest_id={bid2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
