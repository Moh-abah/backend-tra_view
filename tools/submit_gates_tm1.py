#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TP3-TRAILMODE1 — بث بوابات القبول واستطلاعها (بعد النشر).

البوابة أ (هوية تراكمية): تريلينق+تصريف بلا ستوب ⇒ تطابق المرساة الحية
    #10000801 بت-بت (+4.026247223165185% · 16 صفقة) — نفس بوابة TP3 أ.
البوابة ب (قدرة TP3): الستوب+التريلينق+التصريف معًا ⇒ خروجات ستوب حية —
    نفس بوابة TP3 ب (الرقعة تراكمية: TP3-SLTRAIL1 مضمّنة بالكامل).
البوابة ج (قدرة TRAILMODE1): ب + trailing_stop_mode="rise_pct" ⇒ نتائج
    مختلفة عن ب + الصدى يحمل النمط rise_pct.
البوابة د (الافتراضي الصريح): ب + trailing_stop_mode="peak_pct" ⇒ نفس
    أرقام البوابة ب بت-بت (الصريح ≡ الضمني) + الصدى peak_pct.
البوابة ه (تحقق صارم — بث مباشر): قيمة نمط غير قانونية ⇒ 422 برسالة
    عربية (تُبث عند الطلب فقط: submit_e).

Usage: python3 tools/submit_gates_tm1.py [submit|submit_e|poll|all]
"""
import json
import sys
import time
import urllib.request

BASE = "http://161.97.73.254:8000"
RUN = f"{BASE}/api/v1/backtest1/run"
HERE = "/home/z/my-project/trading-system/trailmode1/merge_package"
TERMINAL = {"SUCCESS", "FAILURE", "CANCELLED", "REVOKED"}


def post(url, payload, timeout=90):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        return json.loads(raw.decode("utf-8"))


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        return json.loads(raw.decode("utf-8"))


def clean(p):
    p = json.loads(json.dumps(p))
    for k in list(p.keys()):
        if p[k] is None:
            del p[k]
    return p


def fetch_task(task):
    d = get(f"{BASE}/api/v1/backtest1/tasks?limit=40")
    for t in d.get("data") or []:
        if str(t.get("task_number")) == str(task):
            return t
    return None


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    jobs = [
        ("payloads/payload_TM_gateA_identity.json", "TM1-A-IDENTITY"),
        ("payloads/payload_TM_gateB_both.json", "TM1-B-BOTH-TP3"),
        ("payloads/payload_TM_gateC_rise.json", "TM1-C-RISE"),
        ("payloads/payload_TM_gateD_peak_explicit.json", "TM1-D-PEAK-EXPLICIT"),
    ]

    if phase in ("submit_e",):
        # البوابة ه — قيمة غير قانونية: يجب أن يرفضها السيرفر 422
        p = json.load(open(f"{HERE}/payloads/payload_TM_gateE_reject.json",
                           encoding="utf-8"))
        try:
            resp = post(RUN, clean(p))
            print("[ه] خطأ: الحمولة القيمة غير القانونية قُبلت! (يجب أن تُرفض 422)")
            print(json.dumps(resp, ensure_ascii=False)[:400])
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            print(f"[ه] رُفضت كما هو متوقع: HTTP {e.code}")
            print(body[:400])
        return

    if phase in ("submit", "all"):
        submitted = {}
        for fname, key in jobs:
            payload = json.load(open(f"{HERE}/{fname}", encoding="utf-8"))
            try:
                resp = post(RUN, clean(payload))
                task = ((resp.get("data") or {}).get("task_number")
                        or resp.get("task_number"))
                submitted[key] = {"file": fname, "task": str(task),
                                  "name": payload["name"]}
                print(f"[بث] {key} → مهمة #{task}", flush=True)
            except Exception as e:
                submitted[key] = {"file": fname, "error": str(e)}
                print(f"[فشل بث] {key}: {e}", flush=True)
            time.sleep(2)
        json.dump(submitted, open(f"{HERE}/submitted_gates.json", "w",
                                  encoding="utf-8"), ensure_ascii=False, indent=1)

    if phase in ("poll", "all"):
        submitted = json.load(open(f"{HERE}/submitted_gates.json",
                                   encoding="utf-8"))
        deadline = time.time() + 20 * 60
        results = {}
        while time.time() < deadline:
            pending = []
            for key, meta in submitted.items():
                if key in results and results[key].get("state") in TERMINAL:
                    continue
                task = meta.get("task")
                if not task:
                    continue
                t = fetch_task(task)
                if t is None:
                    pending.append(key)
                    continue
                state = str(t.get("state"))
                results[key] = {
                    "task": task, "state": state,
                    "pnl": t.get("total_pnl_percent"),
                    "trades": t.get("total_trades"),
                    "wr": t.get("win_rate"),
                }
                if state in TERMINAL:
                    print(f"[{key}] {state} · pnl={t.get('total_pnl_percent')} · "
                          f"trades={t.get('total_trades')}", flush=True)
                else:
                    print(f"[{key}] {state} · {t.get('progress')}%", flush=True)
                    pending.append(key)
            if not pending:
                print("البوابات انتهت.", flush=True)
                break
            time.sleep(15)
        json.dump(results, open(f"{HERE}/gates_results.json", "w",
                                encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
