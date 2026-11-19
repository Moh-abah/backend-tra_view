#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QMOM1-FIX1 — التحقق الحي بعد الدمج على السيرفر (نفس اختبار #10000604 الحرفي).

يبث حمولة #10000604 نفسها (كموميه الزخم الاولى + بوابة الزخم) → يستطلع حتى
الاكتمال → ينزّل النتيجة كاملة → يفحص:
  1) momentum_gate موجود وكامل في summary.math_audit
  2) أعمدة الموشرات الـ25 بقيم حقيقية في الشموع البصرية (لا null كامل)
  3) osc_gate و iblocked_* يرصدان
  4) الصفقات قليلة (<= 15 — متوقع 11 على هذه النافذة؛ الأساس كان 46)
  5) كل الأعمدة القديمة موجودة (بلا تقصير)
  6) العدادات متسقة مع الصفقات الفعلية
  7) فحص عيّنة قيم MACD/RSI منطقية

الاستخدام:
    python3 tools/live_verify.py            # الافتراضي: السيرفر أدناه
    BASE=http://161.97.73.254:8000 python3 tools/live_verify.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = os.environ.get("BASE", "http://161.97.73.254:8000").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(HERE, "..", "payloads", "payload_qmom1_mmt_10000604.json")
POLL_INTERVAL = float(os.environ.get("POLL", "5.0"))
TIMEOUT_S = float(os.environ.get("TIMEOUT", "1800"))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), "|", name, ("| " + str(detail)) if detail else "")


def _get(path):
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def _post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def main():
    payload = json.load(open(PAYLOAD, encoding="utf-8"))
    payload = {k: v for k, v in payload.items() if v is not None}
    print("POST /api/v1/backtest1/run —", payload.get("name"))
    sub = _post("/api/v1/backtest1/run", payload)
    print("submit:", json.dumps(sub, ensure_ascii=False)[:300])
    task = sub.get("task_id") or sub.get("task_number") or sub.get("task")
    if task is None:
        print("!! لا task_id في الرد:", sub)
        return 2

    t0 = time.time()
    status = {}
    while time.time() - t0 < TIMEOUT_S:
        try:
            status = _get(f"/api/v1/backtest1/status/{task}")
        except urllib.error.HTTPError as e:
            print("status HTTP", e.code, "— retry")
            time.sleep(POLL_INTERVAL)
            continue
        st = str(status.get("state") or status.get("status") or "").upper()
        prog = status.get("progress") or {}
        print(f"  [{int(time.time() - t0):>4}s] {st:12} {prog.get('percent')}% "
              f"{str(prog.get('message') or '')[:70]}")
        if st in ("SUCCESS", "FAILED", "ERROR", "FAILURE", "REVOKED"):
            break
        time.sleep(POLL_INTERVAL)
    if str(status.get("state", "")).upper() != "SUCCESS":
        print("!! المهمة لم تنجح:", json.dumps(status, ensure_ascii=False)[:400])
        return 2

    bid = status.get("backtest_id")
    res = _get(f"/api/v1/backtest1/get/{bid}")
    print("\nresult downloaded:", len(json.dumps(res)) // 1024, "KB")
    summary = res.get("summary") or {}
    chart = res.get("chart_data") or {}
    vc = chart.get("visual_candles") or []
    sm = summary.get("summary") if isinstance(summary.get("summary"), dict) else summary

    # ---------------------------------------------------- 1) momentum_gate
    math_audit = sm.get("math_audit") or {}
    mg = math_audit.get("momentum_gate")
    check("1 momentum_gate موجود في math_audit", mg is not None,
          f"keys={list(math_audit.keys())}")
    if mg is not None:
        cts = mg.get("counts") or {}
        print("   counts:", json.dumps(cts, ensure_ascii=False))
        print("   time_source:", mg.get("time_source"), "| base_tf:", mg.get("base_tf"),
              "| warmup:", mg.get("warmup_neutral_bars"), "| warn:", mg.get("warning_codes"))
        check("1 العدادات الثلاثية", all(k in cts for k in (
            "quantum_ema_entries", "final_entries", "osc_blocked_entries")), cts)
        check("1 time_source معلن (datetime_index في مسار الباك-تست)",
              bool(mg.get("time_source")), mg.get("time_source"))
        check("1 instances[] بحالات النسخ", len(mg.get("instances") or []) == 7,
              f"n={len(mg.get('instances') or [])}")
        check("1 لا تحذيرات خلل (warmup فقط)",
              set(mg.get("warning_codes") or []) <= {"warmup_neutral"},
              mg.get("warning_codes"))

    # ---------------------------------------------------- 2/3) الأعمدة
    first = vc[0].get("indicators", {}) if vc else {}
    osc_keys = [k for k in first if k.startswith("ind_zzfetqem_osc_")
                and not k.endswith("_gate")]
    old_keys = [k for k in first if k.startswith(("ind_zzfetqem_ema_",
                                                  "ind_zzfetqem_tr_",
                                                  "ind_zzfetqem_zone_",
                                                  "ind_zzfetqem_level_"))]
    check("2 أعمدة الموشرات الـ25 موجودة بالشموع", len(osc_keys) == 25, f"n={len(osc_keys)}")
    check("2 الأعمدة القديمة موجودة (بلا تقصير)", len(old_keys) >= 30, f"n={len(old_keys)}")
    step = max(1, len(vc) // 400)
    nonnull = total = 0
    macd_vals, rsi_vals = [], []
    for c in vc[::step]:
        for k in osc_keys:
            x = c.get("indicators", {}).get(k)
            total += 1
            if x is not None:
                nonnull += 1
                if "_macd_" in k and k.endswith("_line"):
                    macd_vals.append(x)
                if "_rsi_" in k and k.endswith("_value"):
                    rsi_vals.append(x)
    check("2 قيم الموشرات حقيقية في العينة (>70% غير null)",
          total and nonnull / total > 0.7, f"{nonnull}/{total}")
    check("2 MACD قيم منطقية (موجبة وسالبة)", bool(macd_vals)
          and any(v > 0 for v in macd_vals) and any(v < 0 for v in macd_vals))
    check("2 RSI ضمن (0..100)", bool(rsi_vals) and all(0 <= v <= 100 for v in rsi_vals),
          f"min={min(rsi_vals):.1f} max={max(rsi_vals):.1f}" if rsi_vals else "")

    gate_nn = sum(1 for c in vc[::step]
                  if c.get("indicators", {}).get("ind_zzfetqem_osc_gate") is not None)
    blk_nn = sum(1 for c in vc[::step] if any(
        c.get("indicators", {}).get(f"ind_zzfetqem_entry_iblocked{t}") is not None
        for t in ("", "_s1", "_s2", "_s3")))
    check("3 osc_gate يرصد (قيم مفتوحة موجودة)", gate_nn > 0, f"gate_nn={gate_nn}")
    check("3 iblocked_* يرصد (البوابة قتلت دخولات ورسمتها)", blk_nn > 0, f"blk={blk_nn}")

    # ---------------------------------------------------- 4/6) الصفقات
    trades = sm.get("total_trades")
    check("4 الصفقات قليلة بعد البوابة (<=15 — الأساس كان 46)",
          trades is not None and trades <= 15, f"trades={trades}")
    if mg is not None:
        fin = (mg.get("counts") or {}).get("final_entries")
        check("6 final_entries == total_trades (تقرير صادق)", fin == trades,
              f"final={fin} vs trades={trades}")

    print(f"\n===== LIVE: PASS {len(PASS)} / FAIL {len(FAIL)} =====")
    if FAIL:
        print("FAILURES:", FAIL)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
