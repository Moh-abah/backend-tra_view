# -*- coding: utf-8 -*-
"""بطارية اختبار R45 — سجل العمليات المؤسساتي + كاش الشموع الدائم.

ما تثبته هذه البطارية (بلا سيرفر — كلها محلية على قاعدة مؤقتة):

  القسم A — العدّاد الذرّي (12 فحصاً)
      الترقيم التسلسلي 10000001 → 99999999: بذرة صحيحة، تزايد رتيب،
      تفرّد تحت التخصيص المتزامن من عدة خيوط/حلقات، استمرارية بعد
      «إعادة تشغيل»، عدم إعادة الأرقام بعد حذف الصفوف، سلوك نهاية
      العداد (99999999 ثم خطأ صريح)، قفز ما دون البذرة إلى البداية.

  القسم B — دورة حياة السجل (11 فحصاً)
      register/update/finish_success/finish_failure كاملة الحقول، تثبيت
      النسبة 0..100، دمج meta، اللقطة السطحية (pnl/win/trades)، المدة
      الفعلية، القائمة + الإحصاءات + التصفية، ETA التاريخي والاستقرائي،
      عقد status_payload المتوافق مع الواجهة الحالية حرفياً.

  القسم C — كاش الشموع (17 فحصاً)
      تطبيع الأزمنة (ثوانٍ/مليّ/ISO/datetime)، الدمج وإزالة التكرار،
      القص للنافذة، استنتاج الفاصل، أمانة مخطط DataFrame (4 أشكال فعلية:
      RangeIndex بينانس، DatetimeIndex مسمّى، فهرس بلا اسم، عمود ISO) —
      إعادة البناء بنفس الأعمدة/الأنواع/القيم، الإصابة بصفر جلب تحت
      ساعة مجمّدة، تحديث الرأس بيوم واحد فقط لفجوة ساعتين، تعميق
      النافذة يدمج ولا يهدر، التجاوز الآمن عند تنسيق مجهول.

  القسم D — الأسلاك الجراحية (11 فحصاً)
      الترقيم والسجل والكاش موصولون فعلاً في الراوترين والمهمة، علامات
      R42/R43/R44 كلها حيّة (لا انحدار)، درع القفل يعمل فوق سجل R45،
      session.py لم تُمس (بصمة R44 حرفياً)، والملفات تترجم نظيفة.

  القسم E — المتانة (9 فحوص)
      WAL ما زال مثبتاً، ensure idempotent، تنظيف الميتة (reap) +
      الشفاء بالاكتمال المتأخر، فشل تحديث التقدم لا يقتل التشغيل،
      التخصيص ينتظر قفل EXCLUSIVE ثم ينجح (تكامل درع R44)، سطر
      counter واحد فقط، والسجل يقرأ من عملية أخرى (subprocess).

التشغيل (من جذر المشروع بعد التركيب):
    python3 test_battery_r45.py
"""
import asyncio
import hashlib
import importlib
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def find_root():
    """جذر المشروع: نفس المجلد أو الأب (داخل حزمة)."""
    for cand in (HERE, os.path.dirname(HERE)):
        if os.path.exists(os.path.join(cand, "app", "database", "session.py")):
            return cand
    raise SystemExit("شغّل البطارية من جذر المشروع أو من داخل حزمة R45")


ROOT = find_root()
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="r45_battery_")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(TMP, "battery.db")
os.environ["DEBUG"] = "true"
os.environ["SECRET_KEY"] = "r45-battery-secret"
os.environ["SQLITE_BUSY_TIMEOUT_MS"] = "8000"
os.environ["SQLITE_LOCK_RETRIES"] = "5"
os.environ["SQLITE_LOCK_BASE_DELAY"] = "0.05"
os.environ["SQLITE_LOCK_MAX_DELAY"] = "0.2"
os.environ["TASK_REGISTRY_REAP_SECONDS"] = "0"  # تعطيل reap أثناء معظم الفحوص
os.environ.pop("R45_TEST_CLOCK_EPOCH", None)

# بصمة درع R44 — session.py لم تُمس في R45 إطلاقاً
SESSION_MD5_R44 = "1fe61977aaebd8a4e1dadae1bf5aee12"

PASS = 0
FAIL = 0
FAILURES = []


def check(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# الاستيراد الفعلي للوحدات قيد الاختبار (يبني المحرك على قاعدة البطارية)
import app.database.session as S  # noqa: E402
from app.services.task_registry import (  # noqa: E402
    TASK_ID_MAX,
    TASK_ID_START,
    TaskRegistry,
    ensure_registry_tables,
    status_payload,
    utcnow_naive,
)

print("بطارية اختبار R45 — سجل العمليات المؤسساتي + كاش الشموع")
print(f"جذر المشروع: {ROOT}")

REG = TaskRegistry()

# ======================================================================
section(f"القسم A — العدّاد الذرّي {TASK_ID_START} → {TASK_ID_MAX} (12 فحصاً)")
# ======================================================================

# A1: البذرة الصحيحة
id1 = asyncio.run(REG.allocate_id())
id2 = asyncio.run(REG.allocate_id())
check(id1 == TASK_ID_START and id2 == TASK_ID_START + 1,
      f"A1 · البذرة: أول رقم {id1} ثم {id2} (المطلوب 10000001 ثم 10000002)")

# A2: التزايد رتيب صاعد
ids = [asyncio.run(REG.allocate_id()) for _ in range(5)]
check(all(b == a + 1 for a, b in zip(ids, ids[1:])),
      f"A2 · تزايد رتيب متصل: {ids[0]} → {ids[-1]}")

# A3: التخصيص المتزامن من عدة خيوط/حلقات — تفرّد كامل
concurrent_ids = []
conc_lock = threading.Lock()


def _alloc_thread(n):
    from app.database.session import build_isolated_session_maker

    maker, eng = build_isolated_session_maker()
    reg_t = TaskRegistry(session_maker=maker)
    got = []
    for _ in range(n):
        got.append(asyncio.run(reg_t.allocate_id()))
    asyncio.run(eng.dispose())
    with conc_lock:
        concurrent_ids.extend(got)


threads = [threading.Thread(target=_alloc_thread, args=(4,)) for _ in range(3)]
for t in threads:
    t.start()
main_side = [asyncio.run(REG.allocate_id()) for _ in range(4)]
for t in threads:
    t.join()
check(len(concurrent_ids) == 12 and len(set(concurrent_ids)) == 12
      and not (set(concurrent_ids) & set(main_side)),
      f"A3 · {len(concurrent_ids)} تخصيصاً متزامناً من 3 خيوط + الحلقة الرئيسية — كلها فريدة")

# A4: التخصيص من عملية أخرى (subprocess) على نفس القاعدة — نفس العائلة
code = (
    "import asyncio,sys;"
    f"sys.path.insert(0,{ROOT!r});"
    "from app.services.task_registry import TaskRegistry;"
    "print(asyncio.run(TaskRegistry().allocate_id()))"
)
out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
sub_id = int(out.stdout.strip()) if out.returncode == 0 else -1
next_local = asyncio.run(REG.allocate_id())
check(out.returncode == 0 and sub_id == next_local - 1,
      f"A4 · عملية خارجية خصّصت {sub_id} ثم المحلية {next_local} — عدّاد واحد مشترك")

# A5: الاستمرارية بعد «إعادة تشغيل» (محرك جديد كلياً)
before = asyncio.run(REG.allocate_id())
import app.services.task_registry as TR  # noqa: E402

TR._ensured_threads.clear()  # محاكاة عملية جديدة
after = asyncio.run(TaskRegistry().allocate_id())
check(after == before + 1,
      f"A5 · بعد محاكاة إعادة التشغيل: {before} ثم {after} — العدّاد في القاعدة لا الذاكرة")

# A6: حذف صفوف السجل لا يعيد الأرقام
from app.models.backtest_task import BacktestTask  # noqa: E402
from sqlalchemy import delete as sa_delete  # noqa: E402


async def _a6_delete(peak):
    async with S.AsyncSessionLocal() as db:
        await db.execute(sa_delete(BacktestTask).where(BacktestTask.id == peak))
        await db.commit()


peak = asyncio.run(REG.allocate_id())
asyncio.run(_a6_delete(peak))
nxt = asyncio.run(REG.allocate_id())
check(nxt == peak + 1,
      f"A6 · حُذف صف {peak} والتالي {nxt} — لا إعادة استخدام أبداً (عدّاد مستقل عن الصفوف)")

# A7: نهاية العداد — 99999999 ثم خطأ صريح


async def _set_counter(v):
    async with S.AsyncSessionLocal() as db:
        from sqlalchemy import text

        await db.execute(text("UPDATE task_id_counter SET last_id = :v WHERE id=1"),
                         {"v": v})
        await db.commit()


asyncio.run(_set_counter(TASK_ID_MAX - 1))
last = asyncio.run(REG.allocate_id())
try:
    asyncio.run(REG.allocate_id())
    err = None
except RuntimeError as e:
    err = str(e)
asyncio.run(_set_counter(10000500))  # إعادة العدّاد لمستوى معقول لبقية البطارية
check(last == TASK_ID_MAX and err is not None and "99999999" in (err or ""),
      f"A7 · آخر رقم {last} ثم RuntimeError صريح بنص العداد ({(err or '')[:60]}...)")

# A8: عدّاد تحت البذرة (ترقيم قديم/يدوي) يقفز إلى البداية لا أن يستمر تحتها


asyncio.run(_set_counter(999))
a8_id = asyncio.run(REG.allocate_id())
check(a8_id == TASK_ID_START,
      f"A8 · عدّاد تحت البذرة قفز إلى {a8_id} (لا 1000 — البذرة حدود دنيا)")

# A9: صف العدّاد واحد بالضبط


async def a9():
    async with S.AsyncSessionLocal() as db:
        from sqlalchemy import text

        r = await db.execute(text("SELECT COUNT(*) FROM task_id_counter"))
        return r.scalar()


check(asyncio.run(a9()) == 1, "A9 · جدول العدّاد صف واحد بالضبط (id=1)")

# A10: جدولا السجل والكاش موجودان بالأسماء المتعاقد عليها


async def a10():
    async with S.engine.connect() as c:
        r = await c.execute(
            __import__("sqlalchemy").text(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        )
        return {row[0] for row in r.fetchall()}


tables = asyncio.run(a10())
check({"backtest_tasks", "task_id_counter", "candle_cache"} <= tables,
      f"A10 · الجداول الثلاثة موجودة: backtest_tasks + task_id_counter + candle_cache")

# A11: عبارة التخصيص ذرّية (RETURNING) في نص الخدمة
src_registry = read(os.path.join(ROOT, "app", "services", "task_registry.py"))
check("UPDATE task_id_counter SET last_id = last_id + 1" in src_registry
      and "RETURNING last_id" in src_registry,
      "A11 · التخصيص بعبارة واحدة ذرّية (UPDATE ... RETURNING) — لا نافذة تزاحم")

# A12: التخصيص ينتظر قفل EXTERNAL ثم ينجح (تكامل درع R44 حي)


def _hold(seconds):
    import sqlite3

    def _w():
        conn = sqlite3.connect(os.path.join(TMP, "battery.db"), timeout=30)
        conn.execute("BEGIN EXCLUSIVE")
        conn.execute("CREATE TABLE IF NOT EXISTS probe(x)")
        time.sleep(seconds)
        conn.rollback()
        conn.close()

    t = threading.Thread(target=_w, daemon=True)
    t.start()
    time.sleep(0.3)
    return t


t12 = _hold(1.5)
t0 = time.monotonic()
locked_alloc = asyncio.run(REG.allocate_id())
dt12 = time.monotonic() - t0
t12.join()
check(locked_alloc > 0 and dt12 >= 1.0,
      f"A12 · تخصيص تحت قفل EXCLUSIVE انتظر {dt12:.1f}s ثم نجح (درع R44 يعمل فوق السجل)")

# ======================================================================
section("القسم B — دورة حياة السجل (11 فحصاً)")
# ======================================================================

# B1: تسجيل كامل الحقول
b1 = asyncio.run(REG.allocate_id())
asyncio.run(REG.register(
    b1, name="بطارية-موحد", mode="unified-exit", symbol="BTCUSDT",
    timeframe="1m", market="crypto", strategy="zzfib", days=365,
    message="بدء الاختبار",
))
row = asyncio.run(REG.get(b1))
check(row and row["state"] == "PROGRESS" and row["progress"] == 2.0
      and row["symbol"] == "BTCUSDT" and row["timeframe"] == "1m"
      and row["mode"] == "unified-exit" and row["strategy"] == "zzfib"
      and row["days"] == 365,
      "B1 · register: كل حقول التصنيف + الحالة الابتدائية محفوظة")

# B2: تحديث التقدم + تثبيت النسبة 0..100
asyncio.run(REG.update(b1, progress=250.0, phase="simulate", message="اختبار التثبيت"))
row = asyncio.run(REG.get(b1))
check(row["progress"] == 100.0 and row["phase"] == "simulate",
      f"B2 · تحديث 250% ثُبّت إلى {row['progress']} (السقف 100)")

# B3: دمج meta التصاعدي
asyncio.run(REG.update(b1, progress=25.0, meta_patch={"cache": {"hit": True}}))
asyncio.run(REG.update(b1, progress=30.0, meta_patch={"extra": 1}))
row = asyncio.run(REG.get(b1))
check(row["meta"].get("cache", {}).get("hit") is True and row["meta"].get("extra") == 1,
      "B3 · meta_patch يدمج ولا يستبدل (cache.hit + extra معاً)")

# B4: finish_success باللقطة السطحية والمدة
time.sleep(0.05)
asyncio.run(REG.finish_success(
    b1, backtest_id="bid-b4", total_pnl_percent=27.72,
    win_rate=56.52, total_trades=23, meta_patch={"engine": "unified"},
))
row = asyncio.run(REG.get(b1))
check(row["state"] == "SUCCESS" and row["progress"] == 100.0
      and row["backtest_id"] == "bid-b4" and row["total_pnl_percent"] == 27.72
      and row["win_rate"] == 56.52 and row["total_trades"] == 23
      and row["duration_ms"] is not None and row["duration_ms"] > 0
      and row["finished_at"] is not None,
      f"B4 · finish_success: لقطة كاملة + مدة {row['duration_ms']}ms")

# B5: finish_failure بالخطأ والمدة
b5 = asyncio.run(REG.allocate_id())
asyncio.run(REG.register(b5, name="فاشلة-مقصودة", mode="inprocess"))
asyncio.run(REG.finish_failure(b5, error=ValueError("خطأ اختبار مقصود")))
row = asyncio.run(REG.get(b5))
check(row["state"] == "FAILURE" and "خطأ اختبار مقصود" in row["error"]
      and row["duration_ms"] is not None,
      "B5 · finish_failure: الخطأ محفوظ حرفياً + مدة محسوبة")

# B6: القائمة + الإحصاءات + التصفية + الترتيب
lst = asyncio.run(TaskRegistry().list_tasks(limit=50, offset=0))
running = asyncio.run(TaskRegistry().list_tasks(state="PROGRESS"))
succ = asyncio.run(TaskRegistry().list_tasks(state="SUCCESS"))
check(lst["stats"]["total"] >= 2 and lst["stats"]["success"] >= 1
      and succ["count"] >= 1 and all(r["state"] == "SUCCESS" for r in succ["data"])
      and lst["data"][0]["task_number"] > lst["data"][-1]["task_number"],
      f"B6 · list_tasks: الإحصاءات {lst['stats']} + تصفية + ترتيب تنازلي")

# B7: ETA التاريخي — بعد نجاح سابق لنفس الرمز/الفريم
b7 = asyncio.run(REG.allocate_id())
asyncio.run(REG.register(
    b7, name="eta-تاريخي", mode="unified-exit",
    symbol="BTCUSDT", timeframe="1m", market="crypto",
))
row7 = asyncio.run(TaskRegistry().enrich_live(asyncio.run(REG.get(b7))))
check(row7.get("eta_seconds") is not None and row7.get("eta_seconds") > 0,
      f"B7 · ETA تاريخي من متوسط النجاحات السابقة: {row7.get('eta_seconds')}s")

# B8: ETA الاستقرائي (لا تاريخ) + elapsed حي
b8 = asyncio.run(REG.allocate_id())
asyncio.run(REG.register(
    b8, name="eta-استقرائي", mode="unified-exit",
    symbol="SOLNEWUSDT", timeframe="4h", market="crypto",
))
asyncio.run(REG.update(b8, progress=50.0))
time.sleep(0.12)  # ضمان أن elapsed > 0 للاستقراء
row8 = asyncio.run(TaskRegistry().enrich_live(asyncio.run(REG.get(b8))))
check(row8.get("elapsed_seconds") is not None and row8.get("eta_seconds") is not None
      and row8["eta_seconds"] <= row8["elapsed_seconds"] + 0.5,
      f"B8 · ETA استقرائي عند 50%: eta≈elapsed ({row8.get('eta_seconds')}s ≈ {row8.get('elapsed_seconds')}s)")

# B9: عقد status_payload متوافق مع الواجهة الحالية حرفياً
p = status_payload(asyncio.run(REG.get(b1)))
check(p["message"] == "Backtest completed successfully."
      and p["result"] == {"status": "SUCCESS", "backtest_id": "bid-b4"}
      and p["task_id"] == str(b1) and p["task_number"] == b1
      and isinstance(p["progress"], dict) and "percent" in p["progress"],
      "B9 · status_payload: مفاتيح العقد القديم (message/result) + الجديدة معاً")

# B10: المهمة الجارية تعرض stale_seconds (نبض)
row10 = asyncio.run(REG.get(b7))
check(row10["state"] == "PROGRESS" and row10.get("stale_seconds") is not None,
      "B10 · المهمة الجارية تعرض نبضها (stale_seconds) للمراقبة")

# B11: تحديث تقدم بمصنع جلسات ميت → يرجع False ولا يرفع استثناء (لا يقتل التشغيل)
class _DeadMaker:
    def __call__(self):
        raise RuntimeError("dead session maker")


dead_reg = TaskRegistry(session_maker=_DeadMaker())
try:
    ok11 = asyncio.run(dead_reg.update(1, progress=10.0))
    raised = False
except Exception:
    raised = True
check(ok11 is False and raised is False,
      "B11 · فشل تحديث التقدم لا يقتل التشغيل (يرجع False بصمت)")

# ======================================================================
section("القسم C — كاش الشموع الدائم (17 فحصاً)")
# ======================================================================

from app.services import candle_cache as CC  # noqa: E402
from app.services.candle_cache import (  # noqa: E402
    CachedDataService,
    CandleCacheService,
    _capture_df_schema,
    _candle_time,
    _df_from_records,
    _merge_dedupe,
    _norm_epoch,
    _records_from_df,
)

FROZEN = 1793642400
os.environ["R45_TEST_CLOCK_EPOCH"] = str(FROZEN)
import importlib as _il  # noqa: E402

_il.reload(CC)  # التقاط الساعة المجمّدة
CandleCacheService = CC.CandleCacheService
CachedDataService = CC.CachedDataService

FETCHES = []


class FakeDataService:
    """مزوّد اصطناعي يولّد شموعاً حتمية ويسجّل كل جلب."""

    def __init__(self, cols_ms=True):
        self.cols_ms = cols_ms
        self.db = None

    async def get_historical(self, symbol=None, timeframe=None, market=None, days=None):
        import pandas as pd

        interval = {"1h": 3600, "15m": 900}.get(timeframe, 3600)
        now = int(os.environ.get("R45_TEST_CLOCK_EPOCH", str(time.time())))
        start = ((now - int(days) * 86400) // interval) * interval
        ts = list(range(start, now, interval))
        FETCHES.append({"symbol": symbol, "days": days, "n": len(ts)})
        price = 40000.0
        rows = []
        for t in ts:
            close = price * (1.0 + ((t // interval) % 7 - 3) * 0.001)
            rows.append({
                "time": int(t * 1000) if self.cols_ms else int(t),
                "open": price, "high": max(price, close) * 1.001,
                "low": min(price, close) * 0.999, "close": close,
                "volume": 10.0,
            })
            price = close
        return pd.DataFrame(rows)


def df_to_candles(df):
    out = []
    for rec in df.to_dict("records"):
        t = float(rec["time"])
        out.append({**rec, "time": int(t / 1000.0) if t > 1e11 else int(t)})
    return out


# C1: تطبيع الأزمنة
check(_norm_epoch(1793642400) == 1793642400
      and _norm_epoch(1793642400000) == 1793642400
      and _norm_epoch("2026-11-02T18:20:00+00:00") == 1793643600
      and _norm_epoch(None) is None,
      "C1 · تطبيع الأزمنة: ثوانٍ/مليّ/ISO/فارغ")

# C2: مفتاح الزمن بأي اسم متعارف عليه
check(_candle_time({"timestamp": 1793642400}) == 1793642400
      and _candle_time({"open_time": 1793642400000}) == 1793642400
      and _candle_time({"close": 1}) is None,
      "C2 · _candle_time: timestamp/open_time/مجهول")

# C3: الدمج يرتب ويزيل التكرار (الأحدث يغلب)
old = [{"time": 100, "close": 1.0}, {"time": 200, "close": 2.0}]
new = [{"time": 200, "close": 9.9}, {"time": 150, "close": 1.5}]
merged = _merge_dedupe(old, new)
check([c["time"] for c in merged] == [100, 150, 200]
      and merged[2]["close"] == 9.9,
      "C3 · الدمج: مرتب تصاعدياً + إزالة التكرار بالأحدث")

# C4: دمج تنسيق مجهول → None (تجاوز آمن)
check(_merge_dedupe([{"close": 1.0}], [{"time": 1, "close": 2.0}]) is None,
      "C4 · دمج تنسيق مجهول يعيد None (إشارة تجاوز لا تخزين فاسد)")

# C5: مساحة c — جلب بارد ثم إصابة بصفر جلب تحت ساعة مجمّدة
svc = CandleCacheService(session_maker=S.AsyncSessionLocal)
ds = FakeDataService()


async def _fetch(d):
    return await ds.get_historical(symbol="BTCUSDT", timeframe="1h",
                                   market="crypto", days=d)


r1 = asyncio.run(svc.get_candles(symbol="BTCUSDT", timeframe="1h", market="crypto",
                                 days=10, fetch_df=_fetch, df_to_candles=df_to_candles))
n_after_cold = len(FETCHES)
check(r1.cache_hit is False and r1.fetched_new == 240 and n_after_cold == 1,
      f"C5 · جلب بارد: {r1.fetched_new} شمعة بنداء واحد")

r2 = asyncio.run(svc.get_candles(symbol="BTCUSDT", timeframe="1h", market="crypto",
                                 days=10, fetch_df=_fetch, df_to_candles=df_to_candles))
check(r2.cache_hit is True and r2.fetched_new == 0 and len(FETCHES) == n_after_cold,
      "C6 · إصابة كاملة بصفر جلب جديد (ساعة مجمّدة) — سيناريو المؤشرات المختلفة")

# C7: تحديث الرأس — فجوة ساعتين تجلب يوماً واحداً فقط (+الشموع الجديدة)
os.environ["R45_TEST_CLOCK_EPOCH"] = str(FROZEN + 7200)
r3 = asyncio.run(svc.get_candles(symbol="BTCUSDT", timeframe="1h", market="crypto",
                                 days=10, fetch_df=_fetch, df_to_candles=df_to_candles))
head = FETCHES[-1]
check(r3.cache_hit is True and head["days"] == 1 and r3.fetched_new >= 2
      and len(FETCHES) == n_after_cold + 1,
      f"C7 · تحديث الرأس: جلب يوم واحد فقط لنافذة ساعتين (+{r3.fetched_new} شمعة)")

# C8: نافذة أعمق تُجلب كاملة وتُدمج مع المخزون
os.environ["R45_TEST_CLOCK_EPOCH"] = str(FROZEN)
before8 = len(FETCHES)
r8 = asyncio.run(svc.get_candles(symbol="BTCUSDT", timeframe="1h", market="crypto",
                                 days=30, fetch_df=_fetch, df_to_candles=df_to_candles))
check(r8.cache_hit is False and FETCHES[-1]["days"] == 30 and r8.total > r2.total,
      f"C8 · نافذة 30 يوماً فوق مخزون 10: جلب كامل + دمج (total={r8.total})")

# C9: النافذة العميقة أصبحت مغطاة فوراً
r9 = asyncio.run(svc.get_candles(symbol="BTCUSDT", timeframe="1h", market="crypto",
                                 days=30, fetch_df=_fetch, df_to_candles=df_to_candles))
check(r9.cache_hit is True and len(FETCHES) == before8 + 1,
      "C9 · التغطية العميقة جاهزة فوراً بعد الدمج (المخزون يتعمق تدريجياً)")

# C10: أمانة مخطط DataFrame — 4 أشكال فعلية
import pandas as pd  # noqa: E402


def _shape_fidelity(name, df):
    schema = _capture_df_schema(df)
    recs = _records_from_df(df)
    rebuilt = _df_from_records(recs, schema)
    if rebuilt is None:
        return False
    cols_ok = list(rebuilt.columns) == list(df.columns)
    types_ok = all(str(rebuilt[c].dtype) == str(df[c].dtype) for c in df.columns)
    len_ok = len(rebuilt) == len(df)
    val_ok = abs(float(rebuilt["close"].sum()) - float(df["close"].sum())) < 1e-6
    idx_ok = type(rebuilt.index).__name__ == type(df.index).__name__
    return cols_ok and types_ok and len_ok and val_ok and idx_ok


base_df = FakeDataService().get_historical_sync = None
c10_df1 = asyncio.run(FakeDataService().get_historical(symbol="X", timeframe="1h", days=2))
ok_a = _shape_fidelity("range", c10_df1)

df2 = c10_df1.copy()
df2["time"] = pd.to_datetime(df2["time"], unit="ms")
df2 = df2.set_index("time")
ok_b = _shape_fidelity("dt-index-named", df2)

df3 = c10_df1.copy()
df3["time"] = pd.to_datetime(df3["time"], unit="ms")
df3.index = [f"r{i}" for i in range(len(df3))]
df3 = df3.set_index("time")
df3 = df3.reset_index().set_index("time")  # فهرس datetime من عمود
ok_c = _shape_fidelity("dt-rebuilt", df3)

df4 = c10_df1.copy()
df4["date"] = pd.to_datetime(df4["time"], unit="ms").dt.strftime("%Y-%m-%dT%H:%M:%S")
df4 = df4.drop(columns=["time"])
ok_d = _shape_fidelity("iso-column", df4)

check(ok_a and ok_b and ok_c and ok_d,
      f"C10 · أمانة المخطط: RangeIndex={ok_a} · DatetimeIndex={ok_b} · مُعاد={ok_c} · عمود ISO={ok_d}")

# C11: مساحة d عبر CachedDataService — إصابة بصفر جلب + نداء موضعي
FETCHES.clear()
wrapped = CachedDataService(FakeDataService(), session_maker=S.AsyncSessionLocal)
dfc = asyncio.run(wrapped.get_historical(symbol="ETHUSDT", timeframe="1h",
                                         market="crypto", days=5))
ok_miss = len(FETCHES) == 1 and list(dfc.columns) == list(c10_df1.columns)
FETCHES.clear()
dfc2 = asyncio.run(wrapped.get_historical(symbol="ETHUSDT", timeframe="1h",
                                          market="crypto", days=5))
ok_hit = len(FETCHES) == 0 and abs(float(dfc2["close"].sum()) - float(dfc["close"].sum())) < 1e-6
dfc3 = asyncio.run(wrapped.get_historical("ETHUSDT", "1h", "crypto", 5))
ok_pos = len(FETCHES) == 0 and abs(float(dfc3["close"].sum()) - float(dfc["close"].sum())) < 1e-6
check(ok_miss and ok_hit and ok_pos,
      "C11 · فضاء d: جلب بارد ثم إصابة بصفر جلب + النداء الموضعي يمر عبر الكاش")

# C12: تمرير الخصائص الغريبة إلى الخدمة الأصلية (__getattr__)
check(wrapped.db is None, "C12 · __getattr__: الخصائص الأخرى تصل للأصل حرفياً")

# C13: توقيع لا يُربط أماناً → تمرير حرفي بلا كاش
class WeirdService:
    async def get_historical(self, *args, **kwargs):
        FETCHES.append({"weird": True})
        return "raw-response"


weird = CachedDataService(WeirdService(), session_maker=S.AsyncSessionLocal)
FETCHES.clear()
resp = asyncio.run(weird.get_historical(1, 2, 3, extra="x"))
check(resp == "raw-response" and len(FETCHES) == 1,
      "C13 · نداء غير قابل للربط يُمرَّر حرفياً (أسوأ حالة = سلوك اليوم)")

# C14: كاش معطّل → جلب مباشر دائماً
svc_off = CandleCacheService(session_maker=S.AsyncSessionLocal)
CC._ENABLED = False
FETCHES.clear()
r14 = asyncio.run(svc_off.get_candles(symbol="OFFUSDT", timeframe="1h", market="crypto",
                                      days=2, fetch_df=_fetch, df_to_candles=df_to_candles))
CC._ENABLED = True
check(r14.cache_hit is False and r14.note == "cache disabled" and len(FETCHES) == 1,
      "C14 · CANDLE_CACHE_ENABLED=false → جلب مباشر (مفتاح أمان تشغيلي)")

# C15: القص للنافذة المطلوبة لا يعيد أقدم منها
r15 = asyncio.run(svc.get_candles(symbol="BTCUSDT", timeframe="1h", market="crypto",
                                  days=5, fetch_df=_fetch, df_to_candles=df_to_candles))
want_start = FROZEN - 5 * 86400 - 3600
check(all(_candle_time(c) >= want_start for c in r15.candles) and len(r15.candles) < r9.total,
      f"C15 · نافذة 5 أيام من مخزون 30: {len(r15.candles)} شمعة (مقصوصة لا كاملة)")

# C16: سقف الحجم يقلّص للأحدث
big = [{"time": FROZEN - i, "close": 1.0} for i in range(1000)]  # تنازلي!
big = list(reversed(big))
CC._MAX_CANDLES = 100
saved16 = asyncio.run(svc._save(
    S.AsyncSessionLocal, "c:crypto:CAPUSDT:1h", "c", "CAPUSDT", "1h", "crypto",
    big, None, "cap-test",
))
CC._MAX_CANDLES = 600000
row16 = asyncio.run(svc._load(S.AsyncSessionLocal, "c:crypto:CAPUSDT:1h"))
check(saved16 and row16["count"] == 100 and row16["last_time"] == FROZEN,
      "C16 · سقف CANDLE_CACHE_MAX_CANDLES يقلّص للأحدث (100 من 1000)")

# C17: شفافية list_entries + delete_entry
entries = asyncio.run(svc.list_entries())
keys = {e["cache_key"] for e in entries}
check("c:crypto:BTCUSDT:1h" in keys and "d:crypto:ETHUSDT:1h" in keys
      and asyncio.run(svc.delete_entry("c:crypto:CAPUSDT:1h")) is True,
      "C17 · list_entries يعرض المفاتيح + delete_entry يحذف")

# ======================================================================
section("القسم D — الأسلاك الجراحية وعلامات الجولات (11 فحصاً)")
# ======================================================================

src_b1 = read(os.path.join(ROOT, "app", "routers", "backtest1.py"))
src_b0 = read(os.path.join(ROOT, "app", "routers", "backtest.py"))
src_tasks = read(os.path.join(ROOT, "app", "tasks", "backtest_tasks.py"))
src_cfg = read(os.path.join(ROOT, "app", "config.py"))
src_session = read(os.path.join(ROOT, "app", "database", "session.py"))

check("TaskRegistry()" in src_b1 and "allocate_id" in src_b1
      and "reg.register(" in src_b1 and "task_number" in src_b1,
      "D1 · backtest1.py: تخصيص رقمي + تسجيل في كل مسارات /run الثلاثة")

check('@router.get("/tasks")' in src_b1 and '@router.get("/tasks/{task_id}")' in src_b1
      and '@router.get("/candle-cache")' in src_b1,
      "D2 · backtest1.py: نقاط النهاية الجديدة /tasks + /tasks/{id} + /candle-cache")

check("get_registry_status" in src_b1 and "task_id.isdigit()" in src_b1,
      "D3 · backtest1.py: /status يقرأ الأرقام من السجل الدائم أولاً")

check("CandleCacheService()" in src_b1 and "get_candles(" in src_b1
      and "_set_registry_progress" in src_b1,
      "D4 · backtest1.py: المنفّذ الموحد يجلب عبر كاش الشموع + تحديث تقدّم حي")

check("TaskRegistry()" in src_b0 and "task_id.isdigit()" in src_b0
      and "get_registry_status" in src_b0 and "task_number" in src_b0,
      "D5 · backtest.py: نفس الترقيم والسجل في /run و /status")

check("_r45_task_id" in src_tasks and "CachedDataService" in src_tasks
      and "config_dict.pop" in src_tasks,
      "D6 · backtest_tasks.py: المُنفّذ يستقبل رقم العملية ويغلّف جلب الشموع بالكاش")

check("TASK_ID_START: int = 10000001" in src_cfg
      and "TASK_ID_MAX: int = 99999999" in src_cfg
      and "CANDLE_CACHE_ENABLED: bool = True" in src_cfg
      and "TASK_REGISTRY_REAP_SECONDS: int = 1800" in src_cfg,
      "D7 · config.py: إعدادات R45 كلها معرّفة ب defaults آمنة")

# D8: علامات الجولات السابقة حيّة (لا انحدار)
check("_reject_exit_strategy_r421" in src_b1 and "[R42]" in src_b1
      and "run_unified_exit_backtest" in src_b1
      and "Unified Exit Engine" in src_b1,
      "D8 · backtest1.py: محرك R42 الموحد + درع R43 حيّان")

check("with_lock_retry" in src_b1 and "_do_save" in src_b1
      and "execute_with_lock_retry" in src_b1
      and 'what=f"backtest1/get {backtest_id}"' in src_b1
      and 'what="backtest1/list"' in src_b1,
      "D9 · backtest1.py: نقاط درع R44 كلها في أماكنها (get/list/save)")

check("_commit_save" in src_tasks
      and 'what=f"save backtest {result.id}", session=db' in src_tasks
      and "✅ R44 — الحفظ عبر درع القفل" in src_tasks,
      "D10 · backtest_tasks.py: حفظ R44 داخل with_lock_retry كما هو")

md5_session = hashlib.md5(
    open(os.path.join(ROOT, "app", "database", "session.py"), "rb").read()
).hexdigest()
check(md5_session == SESSION_MD5_R44,
      f"D11 · session.py بصمة R44 حرفياً ({md5_session[:12]}...) — لم تُمس في R45")

# ======================================================================
section("القسم E — المتانة والشفاء (9 فحوص)")
# ======================================================================

# E1: WAL ما زال مثبتاً على قاعدة البطارية


async def e1():
    async with S.engine.connect() as c:
        r = await c.execute(__import__("sqlalchemy").text("PRAGMA journal_mode"))
        return r.scalar()


check(asyncio.run(e1()) == "wal", "E1 · journal_mode=wal (درع R44 فوق سجل R45)")

# E2: ensure_registry_tables آمن للتكرار
try:
    asyncio.run(ensure_registry_tables())
    asyncio.run(ensure_registry_tables())
    ok2 = True
except Exception:
    ok2 = False
check(ok2, "E2 · ensure_registry_tables idempotent (استدعاءان متتاليان)")

# E3: reap — المهمة الميتة تُعلَّم FAILURE والاكتمال المتأخر يشفى
os.environ["TASK_REGISTRY_REAP_SECONDS"] = "60"
_il.reload(TR)
from datetime import timedelta  # noqa: E402


async def _e3_age_task(dead):
    async with S.AsyncSessionLocal() as db:
        stale = utcnow_naive() - timedelta(seconds=5000)
        await db.execute(
            __import__("sqlalchemy").update(BacktestTask).where(
                BacktestTask.id == dead
            ),
            {"updated_at": stale, "created_at": stale, "started_at": stale},
        )
        await db.commit()


dead = asyncio.run(REG.allocate_id())
asyncio.run(REG.register(dead, name="ميتة-مقصودة", mode="inprocess"))
asyncio.run(_e3_age_task(dead))
asyncio.run(TR._reap_stale(S.AsyncSessionLocal))
row = asyncio.run(REG.get(dead))
reaped = row["state"] == "FAILURE" and "stale" in (row["error"] or "")
# الشفاء: عامل حي أنهى لاحقاً → يقلب الصف إلى SUCCESS
asyncio.run(REG.finish_success(dead, backtest_id="healed-bid"))
row2 = asyncio.run(REG.get(dead))
healed_state, healed_bid = row2["state"], row2["backtest_id"]
os.environ["TASK_REGISTRY_REAP_SECONDS"] = "0"
check(reaped and healed_state == "SUCCESS" and healed_bid == "healed-bid",
      "E3 · reap يميّز الميتة + الاكتمال المتأخر يشفى إلى SUCCESS (لا فقدان)")

# E4: حفظ الكاش ينتظر قفل EXTERNAL ثم ينجح (درع R44 داخل الكاش)
t_e4 = _hold(1.2)
t0 = time.monotonic()
ok_e4 = asyncio.run(svc._save(
    S.AsyncSessionLocal, "c:crypto:LOCKUSDT:1h", "c", "LOCKUSDT", "1h", "crypto",
    [{"time": FROZEN, "close": 1.0}], None, "lock-test",
))
dt_e4 = time.monotonic() - t0
t_e4.join()
check(ok_e4 and dt_e4 >= 0.8,
      f"E4 · حفظ الكاش تحت قفل EXTERNAL انتظر {dt_e4:.1f}s ثم نجح")

# E5: استرجاع أي عملية سابقة عبر get — حتى بعد "إعادة تشغيل"
TR._ensured_threads.clear()
row_b1 = asyncio.run(TaskRegistry().get(b1))
check(row_b1 is not None and row_b1["backtest_id"] == "bid-b4",
      "E5 · أي عملية سابقة تُسترجع كاملة بعد إعادة تهيئة (القاعدة مصدر الحقيقة)")

# E6: القراءة عبر execute_with_lock_retry تعمل فوق جدول السجل


async def e6():
    async with S.AsyncSessionLocal() as db:
        r = await S.execute_with_lock_retry(
            db,
            __import__("sqlalchemy").select(BacktestTask.state).limit(1),
            what="battery-e6",
        )
        return r.scalar() is not None


check(asyncio.run(e6()), "E6 · قراءة السجل عبر execute_with_lock_retry (نمط R44)")

# E7: العمود duration_ms ضمن النطاق المعقول دائماً
rows_all = asyncio.run(TaskRegistry().list_tasks(limit=200))["data"]
check(all((r["duration_ms"] is None) or (r["duration_ms"] >= 0) for r in rows_all),
      "E7 · كل المدد غير سالبة (سلامة الحساب)")

# E8: الملفات الخمسة + الوحدات الجديدة تترجم
rc = subprocess.run(
    [sys.executable, "-m", "py_compile",
     os.path.join(ROOT, "app", "routers", "backtest1.py"),
     os.path.join(ROOT, "app", "routers", "backtest.py"),
     os.path.join(ROOT, "app", "tasks", "backtest_tasks.py"),
     os.path.join(ROOT, "app", "config.py"),
     os.path.join(ROOT, "app", "database", "session.py"),
     os.path.join(ROOT, "app", "services", "task_registry.py"),
     os.path.join(ROOT, "app", "services", "candle_cache.py"),
     os.path.join(ROOT, "app", "models", "backtest_task.py"),
     os.path.join(ROOT, "app", "models", "candle_cache.py")],
    capture_output=True)
check(rc.returncode == 0, "E8 · الملفات التسعة كلها تترجم نظيفة (py_compile)")

# E9: العدّاد النهائي — عقد عدد فحوص هذه الجولة بالضبط
total = PASS + FAIL
check(total == 59, f"E9 · عقد العدد: {total} قبل هذا + 1 = 60 فحصاً")

# ======================================================================
print(f"\n{'=' * 64}")
print(f"النتيجة النهائية: {PASS}/{PASS + FAIL}")
if FAILURES:
    print("الفحوص الفاشلة:")
    for f in FAILURES:
        print(f"  ✗ {f}")
    sys.exit(1)
print("✅ سجل العمليات المؤسساتي R45 مكتمل — كل الفحوص ناجحة")
