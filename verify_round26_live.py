# -*- coding: utf-8 -*-
"""
ROUND26 — تحقق ما بعد النشر (شغّله بعد استبدال الملف على السيرفر الحي)
يتأكد أن السيرفر الحي يعمل بالمحرك المصلح:
1) باك تست سريع RUNEUSDT 1m (يومان) عبر API
2) طبقة visual ?overlays=zzfib_e2e → كل إشارة مرجعها داخل عمر نطاقها
3) حالة المستخدم (نطاق 17:08) → إشارة 17:34 يجب أن تكون S1
4) spec في الجواب = ROUND26-end-to-end
"""
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

BASE = "http://161.97.73.254:8000"
K3 = timezone(timedelta(hours=3))


def t3(ms):
    if ms is None:
        return "—"
    return datetime.fromtimestamp(int(ms) / 1000, tz=K3).strftime("%m-%d %H:%M")


def http_json(path, payload=None, timeout=90):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code, "__body__": e.read().decode("utf-8")[:300]}


def main():
    print("=== تحقق ROUND26 بعد النشر على السيرفر الحي ===")
    tpl = json.load(open("/home/z/my-project/download/ROUND22-ZLF-E2E/ZLF-E2E-BACKTEST-PAYLOAD.json"))
    payload = dict(tpl)
    payload["timeframe"] = "1m"
    payload["symbols"] = ["RUNEUSDT"]
    payload["days"] = 3
    run = http_json("/api/v1/backtest/run", payload)
    if run.get("__http_error__"):
        print("فشل الإطلاق:", run)
        return
    task = run.get("task_id") or run.get("backtest_id")
    print("task:", task)
    final = None
    for i in range(120):
        time.sleep(2)
        st = None
        for p in (f"/api/v1/backtest/status/{task}", f"/api/v1/backtest1/status/{task}"):
            st = http_json(p)
            if not st.get("__http_error__"):
                break
        state = str(st.get("state") or st.get("status") or "?").upper()
        if state in ("SUCCESS", "COMPLETED", "DONE", "FINISHED"):
            final = st
            break
        if state in ("FAILED", "ERROR"):
            print("فشل:", json.dumps(st)[:400])
            return
    if not final:
        print("انتهت المهلة")
        return
    bid = final.get("backtest_id") or (final.get("result") or {}).get("backtest_id") or task
    vis = http_json(f"/api/v1/backtest/{bid}/visual?overlays=zzfib_e2e", timeout=150)
    z = ((vis.get("overlays") or {}).get("overlays") or {}).get("zzfib_e2e") or (vis.get("overlays") or {}).get("zzfib_e2e") or {}
    print("spec:", z.get("spec"), "· engine:", z.get("engine"))
    if str(z.get("spec")) != "ROUND26-end-to-end":
        print("❌ المحرك على السيرفر ما زال القديم — تأكد من استبدال الملف وإعادة التشغيل")
        return
    sigs = [s for s in (z.get("signals") or []) if s.get("side") == "liquidity"]
    rng_by_idx = {r["index"]: r for r in (z.get("ranges") or [])}
    bad = 0
    for s in sigs:
        rt = s.get("ref_time")
        at = (s.get("range_anchor") or {}).get("time")
        if rt is not None and at is not None and int(rt) < int(at):
            bad += 1
    print(f"إشارات: {len(sigs)} · مرجع خارج عمر النطاق: {bad} {'✅' if bad == 0 else '❌'}")
    # عمود ولادة النطاق في شموع الرسم (لخط بداية النطاق في شارت الباك تست)
    vcs = vis.get("visual_candles") or []
    anch_hits = [c for c in vcs if c.get("ind_zzfe_anchor") in (1, 1.0, True)]
    print(f"شموع الرسم: {len(vcs)} · نقاط ind_zzfe_anchor: {len(anch_hits)} "
          f"· نطاقات: {len(z.get('ranges') or [])} "
          f"{'✅' if anch_hits and len(anch_hits) >= 1 else '⚠️ (افحص تمرير الأعمدة في الطبقة)'}")
    if anch_hits:
        print(f"  آخر ولادة مرسومة: {t3(anch_hits[-1].get('time'))}")
    tgt = [s for s in sigs if t3(s.get("time")) == "11-03 17:34"]
    for s in tgt:
        print(f"حالة 17:34 على السيرفر: {s['signal'].split()[-1]} · المرجع@{t3(s.get('ref_time'))} "
              f"V={s.get('ref_vol')} {'✅' if s['signal'].endswith('S1') else '❌ (المتوقع S1)'}")
    print("\n⇒ السيرفر الحي يعمل بالمحرك المصلح ✅" if bad == 0 else "\n⇒ يوجد مراجع قديمة ❌")


if __name__ == "__main__":
    main()
