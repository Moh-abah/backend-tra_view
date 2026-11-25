#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""بث المهمة الكاملة (خروج كسر EMA100 + دخول ثانٍ) بعد نشر حزمة EBREAK1.

الاستعمال (بعد نشر الحزمة ونجاح بطارية verify_ebreak_reclaim.py 12/12):
    python3 tools/submit_full_after_deploy.py
"""
import json, sys, time, gzip, urllib.request

BASE = "http://161.97.73.254:8000"
RUN = f"{BASE}/api/v1/backtest1/run"
STATUS = f"{BASE}/api/v1/backtest1/status"
HERE = "/home/z/my-project/trading-system/ebreak-reclaim"
PAYLOAD = f"{HERE}/package/payloads/payload_GOLD_EBREAK_RECLAIM_THETAUSDT.json"
TERMINAL = {"SUCCESS", "FAILURE", "CANCELLED", "REVOKED"}

def post(url, payload, timeout=90):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            try: raw = gzip.decompress(raw)
            except OSError: pass
        return json.loads(raw.decode("utf-8"))

def get(url, timeout=120):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            try: raw = gzip.decompress(raw)
            except OSError: pass
        return json.loads(raw.decode("utf-8"))

def main():
    payload = json.load(open(PAYLOAD, encoding="utf-8"))
    payload = {k: v for k, v in payload.items() if v is not None}
    resp = post(RUN, payload)
    task = resp.get("task_number")
    print("TASK_NUMBER:", task)
    json.dump(resp, open(f"{HERE}/results/submit_full_resp.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if task is None:
        return 1
    t0 = time.time()
    last = None
    while True:
        try:
            st = get(f"{STATUS}/{task}")
        except Exception as e:
            print("poll err:", e); time.sleep(10); continue
        cur = (st.get("state"), st.get("progress", {}).get("percent"))
        if cur != last:
            print(f"[{int(time.time()-t0)}s] {cur[0]} {cur[1]}%")
            last = cur
        if st.get("state") in TERMINAL:
            print("FINAL:", json.dumps(st.get("summary_stats") or {}, ensure_ascii=False))
            json.dump(st, open(f"{HERE}/results/live_full.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            return 0 if st.get("state") == "SUCCESS" else 1
        time.sleep(15)

if __name__ == "__main__":
    sys.exit(main())
