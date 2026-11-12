# -*- coding: utf-8 -*-
"""الإثبات الحي R45 — عقد HTTP كامل فوق راوترات حقيقية.

يشغّل سيرفر FastAPI حقيقاً (run_sandbox.py) بالملفات الفعلية لج45 فوق
ستُبّات المحرك فقط (المحرك المحروس ملك مصدر المستخدم الكامل)، ثم يثبت
حرفياً على HTTP:

  1  الترقيم التسلسلي 10000001 ثم 10000002 ... (لا مزيد من f397b2fa)
  2  دورة حياة كاملة: تقدّم حي + نسبة + رسائل عربية + مدة + ETA
  3  الكاش: الجلب البارد مرة واحدة ثم صفر جلب، وتحديث الرأس بيوم واحد
  4  حفظ دائم: كل نتيجة تُقرأ من القاعدة عبر /get بعد الاكتمال
  5  المسارات الثلاثة: موحد ج42 + قياسي داخل العملية + راوتر backtest
  6  المكتبة: /tasks بالإحصاءات واللقطة السطحية والترتيب
  7  التزامن: 6 عمليات متوازية + قارئان — أرقام فريدة وصفر أخطاء
  8  البقاء: السجل والكاش والعدّاد يبقون بعد إعادة تشغيل السيرفر
  9  الانحدار: درع 422 (R43) حي + العقد القديم (hex status) سليم
  10 wait=true يعيد النتيجة كاملة في نفس الرد

التشغيل:  python3 prove_r45.py   (يدير سيرفره الخاص على منفذ مؤقت)
"""
import concurrent.futures
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8115
BASE = f"http://127.0.0.1:{PORT}"
FROZEN = 1793642400

PASS = 0
FAIL = 0


def check(cond, label, detail=""):
    global PASS, FAIL
    mark = "✅" if cond else "❌"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))


def get(path, timeout=30):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def post(path, body, timeout=60, raw=False):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read().decode()
            return r.status, (r if raw else json.loads(data))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def delete(path, timeout=20):
    req = urllib.request.Request(BASE + path, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def wait_state(task_id, want=("SUCCESS", "FAILURE"), timeout=90):
    t0 = time.monotonic()
    last = {}
    while time.monotonic() - t0 < timeout:
        _, last = get(f"/api/v1/backtest1/status/{task_id}")
        if last.get("state") in want:
            return last
        time.sleep(0.3)
    return last


def boot_server(db_dir):
    env = dict(os.environ)
    env.update({
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_dir}/prove.db",
        "DEBUG": "true",
        "SECRET_KEY": "r45-prove-secret",
        "R45_TEST_CLOCK_EPOCH": str(FROZEN),
        "SANDBOX_PORT": str(PORT),
        "TASK_REGISTRY_REAP_SECONDS": "0",
    })
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "run_sandbox.py")],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        cwd=HERE,
    )
    for _ in range(60):
        try:
            get("/api/v1/backtest1/tasks", timeout=2)
            return proc
        except Exception:
            time.sleep(0.4)
    proc.kill()
    raise SystemExit("السيرفر لم يقلع خلال 24 ثانية")


def unified_body(name, days=10, trailing=True, strategy="zzfib"):
    body = {
        "symbols": ["BTCUSDT"], "timeframe": "1h", "days": days,
        "name": name, "strategy_config": {"name": strategy},
    }
    if trailing:
        body["exit_strategy"] = {
            "strategy": strategy,
            "config": {"use_trailing": True, "trailing_giveback_pct": 20.0},
        }
    return body


print(f"الإثبات الحي R45 — سيرفر حقيقي على المنفذ {PORT}")
print("=" * 64)

db_dir = tempfile.mkdtemp(prefix="r45_prove_")
server = boot_server(db_dir)
try:
    # ------------------------------------------------------------------
    print("\n[1] الترقيم التسلسلي + دورة الحياة الكاملة")
    code, r1 = post("/api/v1/backtest1/run", unified_body("R45-A-sequential"))
    check(code == 200 and r1.get("task_id") == "10000001"
          and r1.get("task_number") == 10000001
          and isinstance(r1.get("progress"), dict)
          and "status" in r1.get("poll", ""),
          "1.1 · أول عملية برقم 10000001 (لا uuid عشوائي) + عقد التقدم")

    st = wait_state("10000001")
    check(st.get("state") == "SUCCESS" and st.get("backtest_id"),
          "1.2 · اكتملت وحُفظت مع backtest_id")
    check(st.get("progress", {}).get("percent") == 100.0
          and st.get("duration_ms") is not None
          and st.get("elapsed_seconds") is not None,
          f"1.3 · نسبة 100% + مدة {st.get('duration_ms')}ms + زمن منقضٍ")
    sm = st.get("summary_stats") or {}
    cache1 = (st.get("meta") or {}).get("cache") or {}
    check(sm.get("total_trades") is not None and sm.get("win_rate") is not None,
          f"1.4 · لقطة سطحية للمكتبة: pnl={sm.get('total_pnl_percent')}% "
          f"WR={sm.get('win_rate')}% صفقات={sm.get('total_trades')}")
    check(cache1.get("hit") is False and cache1.get("fetched_new", 0) > 0,
          f"1.5 · جلب بارد أول مرة: {cache1.get('fetched_new')} شمعة بنداء واحد")

    code, doc = get(f"/api/v1/backtest1/get/{st['backtest_id']}")
    vc = ((doc.get("chart_data") or {}).get("visual_candles")) or []
    check(code == 200 and len(vc) > 0,
          f"1.6 · النتيجة تُقرأ كاملة من القاعدة: {len(vc)} شمعة عبر /get")

    # ------------------------------------------------------------------
    print("\n[2] الكاش — سيناريو المستخدم الحرفي: مؤشرات واستراتيجية مختلفة")
    code, r2 = post("/api/v1/backtest1/run",
                    unified_body("R45-B-different-indicators", strategy="zzfib_e2e"))
    check(r2.get("task_id") == "10000002", "2.1 · العملية الثانية 10000002")
    st2 = wait_state("10000002")
    cache2 = (st2.get("meta") or {}).get("cache") or {}
    check(st2.get("state") == "SUCCESS" and cache2.get("hit") is True
          and cache2.get("fetched_new") == 0,
          f"2.2 · استراتيجية مختلفة = صفر جلب جديد ({cache2.get('note')})")

    post("/sandbox/_test/control", {"R45_TEST_CLOCK_EPOCH": FROZEN + 7200})
    code, r3 = post("/api/v1/backtest1/run", unified_body("R45-C-head-refresh"))
    st3 = wait_state("10000003")
    cache3 = (st3.get("meta") or {}).get("cache") or {}
    check(st3.get("state") == "SUCCESS" and cache3.get("hit") is True
          and cache3.get("fetched_new", 0) >= 2
          and "head refresh" in str(cache3.get("note")),
          f"2.3 · بعد ساعتين: جلب الرأس فقط (+{cache3.get('fetched_new')} شمعة "
          f"— {cache3.get('note')})")
    post("/sandbox/_test/control", {"R45_TEST_CLOCK_EPOCH": FROZEN})

    # ------------------------------------------------------------------
    print("\n[3] المسار القياسي عبر الراوترين + فضاء DataFrame")
    code, r4 = post("/api/v1/backtest1/run", unified_body("R45-D-std-b1", trailing=False))
    st4 = wait_state(r4.get("task_id"))
    check(r4.get("task_id") == "10000004" and st4.get("state") == "SUCCESS"
          and st4.get("mode") == "inprocess",
          "3.1 · مسار قياسي (بلا exit_strategy) داخل العملية — 10000004")

    code, r5 = post("/api/v1/backtest/run", unified_body("R45-E-std-b0", trailing=False))
    tid5 = r5.get("task_id")
    st5 = wait_state(f"/api/v1/backtest/status/{tid5}".replace(
        f"/api/v1/backtest/status/{tid5}", "") or "") if False else None
    # انتظار عبر راوتر backtest نفسه
    t0 = time.monotonic()
    while time.monotonic() - t0 < 60:
        _, s5 = get(f"/api/v1/backtest/status/{tid5}")
        if s5.get("state") in ("SUCCESS", "FAILURE"):
            break
        time.sleep(0.3)
    check(tid5 == "10000005" and s5.get("state") == "SUCCESS"
          and s5.get("task_number") == 10000005,
          "3.2 · راوتر backtest القياسي: 10000005 + /status الرقمي يعمل")

    code, r6 = post("/api/v1/backtest/run", unified_body("R45-F-std-hot", trailing=False))
    tid6 = r6.get("task_id")
    t0 = time.monotonic()
    while time.monotonic() - t0 < 60:
        _, s6 = get(f"/api/v1/backtest/status/{tid6}")
        if s6.get("state") in ("SUCCESS", "FAILURE"):
            break
        time.sleep(0.3)
    cache6 = (s6.get("meta") or {}).get("cache") or {}
    check(s6.get("state") == "SUCCESS" and cache6.get("hit") is True
          and cache6.get("fetched_new") == 0,
          f"3.3 · كاش فضاء DataFrame: صفر جلب للرمز نفسه ({cache6.get('note')})")

    # ------------------------------------------------------------------
    print("\n[4] التقدم الحي أثناء محاكاة بطيئة + ETA")
    post("/sandbox/_test/control", {"SANDBOX_SIM_DELAY": "4"})
    code, r7 = post("/api/v1/backtest1/run", unified_body("R45-G-slow"))
    tid7 = r7.get("task_id")
    time.sleep(1.4)
    _, mid = get(f"/api/v1/backtest1/status/{tid7}")
    prog = mid.get("progress") or {}
    check(mid.get("state") == "PROGRESS" and (prog.get("percent") or 0) >= 10
          and mid.get("elapsed_seconds", 0) > 0.5,
          f"4.1 · أثناء المحاكاة: {prog.get('percent')}% مرحلة={prog.get('phase')} "
          f"منقضٍ={mid.get('elapsed_seconds')}s")
    time.sleep(1.2)
    _, mid2 = get(f"/api/v1/backtest1/status/{tid7}")
    check(mid2.get("elapsed_seconds", 0) > mid.get("elapsed_seconds", 0),
          f"4.2 · الزمن المنقضٍ يتقدم حياً ({mid.get('elapsed_seconds')} → "
          f"{mid2.get('elapsed_seconds')}s)")
    st7 = wait_state(tid7, timeout=60)
    post("/sandbox/_test/control", {"SANDBOX_SIM_DELAY": None})
    check(st7.get("state") == "SUCCESS", "4.3 · البطيئة اكتملت بنجاح بعد الانتظار")

    # التشغيل الثاني لنفس الرمز/الفريم: ETA تاريخي
    post("/sandbox/_test/control", {"SANDBOX_SIM_DELAY": "3"})
    code, r8 = post("/api/v1/backtest1/run", unified_body("R45-H-eta"))
    time.sleep(1.0)
    _, mid8 = get(f"/api/v1/backtest1/status/{r8.get('task_id')}")
    post("/sandbox/_test/control", {"SANDBOX_SIM_DELAY": None})
    check(mid8.get("eta_seconds") is not None,
          f"4.4 · ETA من متوسط العمليات الناجحة السابقة: {mid8.get('eta_seconds')}s")
    wait_state(r8.get("task_id"), timeout=60)

    # ------------------------------------------------------------------
    print("\n[5] المكتبة /tasks + التفاصيل + الشفافية")
    code, tasks = get("/api/v1/backtest1/tasks?limit=100")
    nums = [d["task_number"] for d in tasks.get("data", [])]
    check(code == 200 and tasks.get("stats", {}).get("total") >= 8
          and nums == sorted(nums, reverse=True)
          and all("win_rate" in d and "duration_ms" in d and "state" in d
                  for d in tasks.get("data", [])),
          f"5.1 · المكتبة: {tasks['stats']['total']} عملية مرتبة تنازلياً بحقول كاملة")
    code, one = get("/api/v1/backtest1/tasks/10000001")
    check(code == 200 and one.get("task_number") == 10000001
          and one.get("state") == "SUCCESS",
          "5.2 · /tasks/10000001 يعيد تفاصيل العملية الأولى")
    code, _miss = get("/api/v1/backtest1/tasks/19999999")
    check(code == 404, "5.3 · رقم غير موجود → 404 صريح")
    code, cc = get("/api/v1/backtest1/candle-cache")
    keys = {e["cache_key"] for e in cc.get("data", [])}
    check(code == 200 and any(k.startswith("c:") for k in keys)
          and any(k.startswith("d:") for k in keys),
          f"5.4 · شفافية الكاش: {len(keys)} مفتاحاً (فضاء c و d معاً)")
    code, _ = get("/api/v1/backtest1/list?limit=5")
    check(code == 200, "5.5 · /list القديم يعمل (توافق R44)")

    # ------------------------------------------------------------------
    print("\n[6] wait=true — النتيجة كاملة في نفس الرد")
    code, w = post("/api/v1/backtest1/run?wait=true&wait_timeout=60",
                   unified_body("R45-I-wait"))
    wsm = w.get("summary") or {}
    wcd = w.get("chart_data") or {}
    check(code == 200 and w.get("status") == "COMPLETED"
          and wsm.get("total_trades") is not None and len(wcd.get("visual_candles") or []) > 0,
          f"6.1 · وضع الانتظار: COMPLETED + ملخص + {len(wcd.get('visual_candles') or [])} شمعة بنفس الرد")

    # ------------------------------------------------------------------
    print("\n[7] التزامن — 6 عمليات متوازية + قارئان لا يتوقفان")

    def _unified(i):
        c, r = post("/api/v1/backtest1/run", unified_body(f"R45-stress-{i}"))
        return r.get("task_id")

    def _std(i):
        c, r = post("/api/v1/backtest1/run",
                    unified_body(f"R45-stress-std-{i}", trailing=False))
        return r.get("task_id")

    def _reader(_):
        ok = 0
        t0 = time.monotonic()
        while time.monotonic() - t0 < 6:
            try:
                c, _ = get("/api/v1/backtest1/tasks?limit=10", timeout=10)
                if c == 200:
                    ok += 1
            except Exception:
                pass
            time.sleep(0.2)
        return ok

    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as ex:
        futs = {}
        for i in range(3):
            futs[f"u{i}"] = ex.submit(_unified, i)
        for i in range(3):
            futs[f"s{i}"] = ex.submit(_std, i)
        futs["r1"] = ex.submit(_reader, 0)
        futs["r2"] = ex.submit(_reader, 0)
        res = {k: f.result(timeout=180) for k, f in futs.items()}

    tids = [v for k, v in res.items() if k not in ("r1", "r2")]
    nums7 = sorted(int(x) for x in tids)
    states7 = {}
    for t in tids:
        states7[t] = wait_state(t).get("state")
    check(len(set(tids)) == 6 and nums7 == list(range(nums7[0], nums7[0] + 6)),
          f"7.1 · 6 أرقام متسلسلة فريدة بلا تصادم: {nums7[0]} → {nums7[-1]}")
    check(all(v == "SUCCESS" for v in states7.values()),
          f"7.2 · الست كلها SUCCESS تحت التزامن الكامل")
    check(res["r1"] >= 20 and res["r2"] >= 20,
          f"7.3 · القارئان عبرا {res['r1']}+{res['r2']} قراءة بلا أي انكسار")

    # ------------------------------------------------------------------
    print("\n[8] البقاء بعد إعادة التشغيل — القاعدة مصدر الحقيقة")
    _, before = get("/api/v1/backtest1/tasks?limit=200")
    before_total = before["stats"]["total"]
    last_number = max(d["task_number"] for d in before["data"])
    server.terminate()
    server.wait(timeout=15)
    server = boot_server(db_dir)
    code, after = get("/api/v1/backtest1/tasks?limit=200")
    check(after["stats"]["total"] == before_total,
          f"8.1 · بعد إعادة التشغيل: {after['stats']['total']} عملية كما كانت (لا ضياع)")
    code, r9 = post("/api/v1/backtest1/run", unified_body("R45-J-after-restart"))
    check(r9.get("task_number") == last_number + 1,
          f"8.2 · العدّاد واصل من حيث توقف: {last_number} → {r9.get('task_number')}")
    st9 = wait_state(r9.get("task_id"))
    cache9 = (st9.get("meta") or {}).get("cache") or {}
    check(st9.get("state") == "SUCCESS" and cache9.get("hit") is True,
          f"8.3 · الكاش نفسه بقي: {cache9.get('note')}")

    # ------------------------------------------------------------------
    print("\n[9] الانحدار — دروع الجولات السابقة حيّة")
    code9, _ = post("/api/v1/backtest1/walk-forward", {
        "symbols": ["BTCUSDT"], "timeframe": "1h", "days": 10,
        "strategy_config": {"name": "zzfib"},
        "exit_strategy": {"strategy": "zzfib", "config": {"use_trailing": True}},
    })
    check(code9 == 422, "9.1 · درع الصراحة R43: exit_strategy خارج المسار الموحد → 422")
    code9b, _ = post("/api/v1/backtest/run", {
        "symbols": ["BTCUSDT"], "timeframe": "1h", "days": 10,
        "strategy_config": {"name": "zzfib"},
        "exit_strategy": {"strategy": "zzfib", "config": {"use_trailing": True}},
    })
    check(code9b == 422, "9.2 · درع الصراحة في راوتر backtest → 422")
    _, legacy = get("/api/v1/backtest1/status/f397b2fa1234")
    check(legacy.get("state") in ("PENDING", "UNKNOWN"),
          f"9.3 · معرّف سداسي قديم → العقد القديم يعمل ({legacy.get('state')})")
    _, st1 = get("/api/v1/backtest1/status/10000001")
    sm1 = st1.get("summary") if isinstance(st1.get("summary"), dict) else {}
    check(st1.get("message") == "Backtest completed successfully."
          and isinstance(st1.get("result"), dict),
          "9.4 · مفاتيح العقد القديم (message/result) موجودة في الرد الرقمي")

    # ------------------------------------------------------------------
    print("\n[10] حذف كاش + إعادة الجلب الذاتي")
    code, _ = delete("/api/v1/backtest1/candle-cache/c:crypto:BTCUSDT:1h")
    check(code == 200, "10.1 · حذف مفتاح كاش يعمل")
    code, r10 = post("/api/v1/backtest1/run", unified_body("R45-K-after-cache-clear"))
    st10 = wait_state(r10.get("task_id"))
    cache10 = (st10.get("meta") or {}).get("cache") or {}
    check(st10.get("state") == "SUCCESS" and cache10.get("hit") is False
          and cache10.get("fetched_new", 0) > 0,
          "10.2 · بعد الحذف: جلب كامل جديد ثم يخزن من جديد (ذاتية الشفاء)")

finally:
    try:
        server.terminate()
        server.wait(timeout=10)
    except Exception:
        server.kill()
    shutil.rmtree(db_dir, ignore_errors=True)

print(f"\n{'=' * 64}")
print(f"خلاصة الإثبات الحي R45: {PASS}/{PASS + FAIL}")
if FAIL:
    sys.exit(1)
print("✅ سجل العمليات المؤسساتي + كاش الشموع يعملان حيّاً فوق HTTP حقيقي")
print("   (راوترات ج45 الفعلية فوق ستُبّات محرك — المحرك الحقيقي محروس في مصدر المستخدم)")
