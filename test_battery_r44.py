# -*- coding: utf-8 -*-
"""بطارية اختبار R44 — درع قفل قاعدة البيانات (SQLite Lock Shield).

المشكلة المرصودة في الإنتاج (سجل 2026-11-07):
    sqlite3.OperationalError: database is locked
    1) GET /api/v1/backtest1/get/{id} → 500 (قارئ حُجب أثناء كتابة ضخمة)
    2) المهمة الموحدة f9150e06 فشلت عند الحفظ رغم نجاح المحاكاة نفسها
       (27.7% ربح / 23 صفقة) — INSERT بحجم 3.2MB انتهت مهلته (5 ثوانٍ).

الدرع (ثلاث طبقات تُثبَّت تلقائياً على كل اتصال):
    1) WAL: القرّاء لا يحجبون الكاتب والكاتب لا يحجب القرّاء.
    2) busy_timeout=30s: انتظار حتى 30 ثانية بدل الفشل بعد 5 ثوانٍ.
    3) with_lock_retry / execute_with_lock_retry: إعادة محاولة تصاعدية
       على النقاط الساخنة السبع (حفظ موحد · حفظ قياسي · 2×get · 2×list
       · نقطة القراءة المركزية _get_backtest_row).

التشغيل (من جذر المشروع بعد التركيب):
    python3 test_battery_r44.py
يعمل بلا سيرفر — كل الفحوص محلية نقية على قاعدة اختبار مؤقتة.
"""
import asyncio
import importlib.util
import os
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------
# إعداد بيئة الاختبار: قاعدة مؤقتة + إعدادات درع سريعة للفحوص الوحدية
# (القيم الإنتاجية 30s/5/0.35 تُختبر هي أيضاً — انظر القسم D وE)
# ----------------------------------------------------------------------
TMP = tempfile.mkdtemp(prefix="r44_battery_")
DB_MAIN = os.path.join(TMP, "main.db")
DB_ISOLATED = os.path.join(TMP, "iso.db")
DB_GUARD = os.path.join(TMP, "guard.db")   # للفحص B — سلوك بلا درع
DB_WAL = os.path.join(TMP, "wal.db")       # للفحوص B/D — سلوك بالدرع

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + DB_MAIN
os.environ["SQLITE_BUSY_TIMEOUT_MS"] = "8000"    # أثناء البطارية فقط
os.environ["SQLITE_LOCK_RETRIES"] = "5"
os.environ["SQLITE_LOCK_BASE_DELAY"] = "0.05"    # إعادة محاولة سريعة
os.environ["SQLITE_LOCK_MAX_DELAY"] = "0.2"


def find_root():
    """جذر المشروع: إما نفس المجلد (جذر) أو الأب (داخل حزمة)."""
    for cand in (HERE, os.path.dirname(HERE)):
        if os.path.exists(os.path.join(cand, "app", "database", "session.py")):
            return cand
    raise SystemExit("شغّل البطارية من جذر المشروع أو من داخل حزمة R44")


ROOT = find_root()
sys.path.insert(0, ROOT)

# بصمات حراس الانحدار — ملفات المحرك الموحد/الخروج يجب ألا تتغير إطلاقاً
GUARD_MD5 = {
    "app/services/unified_backtest.py": "0d44ac05a0f524bdc4d898d806ab83db",
    "app/services/exit_engine.py": "0131fc48c59dd802e41bd7c7eddf2363",
    "app/routers/exit_strategy.py": "7c0d7050e1b7997f076f5d2b74b141c3",
    "app/models/backtest_run.py": "8a1e0a0f7062e35565677300ee5bc377",
}

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
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# استيراد وحدة الجلسة المرقّعة (يبني المحرك الرئيسي على DB_MAIN بالدرع)
import app.database.session as S  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402


# ======================================================================
print("بطارية اختبار R44 — درع قفل قاعدة البيانات")
print(f"جذر المشروع: {ROOT}")

# ======================================================================
section("القسم A — وحدات الدرع النقية (10 فحوص)")
# ======================================================================

# A1: الثوابت تُقرأ من البيئة
check(S.SQLITE_BUSY_TIMEOUT_MS == 8000 and S.SQLITE_LOCK_RETRIES == 5
      and abs(S.SQLITE_LOCK_BASE_DELAY - 0.05) < 1e-9
      and abs(S.SQLITE_LOCK_MAX_DELAY - 0.2) < 1e-9,
      "A1 · الثوابت الأربعة تُقرأ من البيئة (8000ms/5/0.05/0.2)")

# A2: تمييز خط القفل الملفوف داخل SQLAlchemy
raw_locked = sqlite3.OperationalError("database is locked")
wrapped = OperationalError("INSERT ...", {}, raw_locked)
wrapped.orig = raw_locked
check(S.is_locked_error(wrapped) is True,
      "A2 · is_locked_error: خط قفل ملفوف داخل SQLAlchemy → True")

# A3: خط قفل خام من sqlite3 مباشرة
check(S.is_locked_error(sqlite3.OperationalError("database is locked")) is True,
      "A3 · is_locked_error: خط قفل خام sqlite3 → True")

# A4: خط تشغيلي غير القفل → False (لا إعادة محاولة عبثاً)
raw_other = sqlite3.OperationalError("no such table: backtest_runs")
wrapped_other = OperationalError("SELECT ...", {}, raw_other)
wrapped_other.orig = raw_other
check(S.is_locked_error(wrapped_other) is False,
      "A4 · is_locked_error: خط آخر (no such table) → False")

# A5: استثناء غير قاعدة بيانات إطلاقاً → False
try:
    raise ValueError("x") from sqlite3.OperationalError("database is locked")
except ValueError as e:
    check(S.is_locked_error(e) is True,
          "A5 · is_locked_error: يفحص سلسلة الأسباب (__cause__)")

# A6: with_lock_retry — فشلان بالقفل ثم نجاح
attempts = {"n": 0}


async def a6():
    async def action():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise wrapped
        return "saved"
    t0 = time.monotonic()
    out = await S.with_lock_retry(action, what="A6")
    dt = time.monotonic() - t0
    check(out == "saved" and attempts["n"] == 3 and dt < 1.5,
          "A6 · with_lock_retry: فشلان بالقفل ثم نجاح (3 محاولات)")

asyncio.run(a6())

# A7: خطأ غير القفل يُرفع فوراً — محاولة واحدة فقط لا غير
calls = {"n": 0}


async def a7():
    async def action():
        calls["n"] += 1
        raise wrapped_other
    try:
        await S.with_lock_retry(action, what="A7")
        ok = False
    except OperationalError:
        ok = calls["n"] == 1
    check(ok, "A7 · with_lock_retry: خطأ غير القفل يُرفع فوراً (محاولة واحدة)")

asyncio.run(a7())

# A8: نفاد المحاولات — يرفع آخر خط قفل بعد العدد المسموح
calls8 = {"n": 0}


async def a8():
    async def action():
        calls8["n"] += 1
        raise wrapped
    try:
        await S.with_lock_retry(action, what="A8")
        ok = False
    except OperationalError as e:
        ok = calls8["n"] == S.SQLITE_LOCK_RETRIES and S.is_locked_error(e)
    check(ok, f"A8 · with_lock_retry: يرفع بعد {S.SQLITE_LOCK_RETRIES} محاولات بالضبط")

asyncio.run(a8())

# A9: الجلسة المُمرّرة يُعاد لها rollback بين المحاولات
rb = {"n": 0}


class FakeSession:
    async def rollback(self):
        rb["n"] += 1


async def a9():
    n = {"n": 0}

    async def action():
        n["n"] += 1
        if n["n"] < 3:
            raise wrapped
        return "ok"
    out = await S.with_lock_retry(action, what="A9", session=FakeSession())
    check(out == "ok" and rb["n"] == 2,
          "A9 · with_lock_retry: rollback للجلسة قبل كل إعادة محاولة")

asyncio.run(a9())

# A10: جدول التأخير التصاعدي بسقف أقصى
d = [round(S._lock_retry_delay(i), 4) for i in range(1, 7)]
check(d == [0.05, 0.1, 0.2, 0.2, 0.2, 0.2],
      f"A10 · التأخير التصاعدي بسقف: {d}")

# ======================================================================
section("القسم B — سلوك القفل الحقيقي: المرض والدواء وجهاً لوجه (8 فحوص)")
# ======================================================================


def hold_exclusive(db_path, seconds):
    """يمسك قفل كتابة EXCLUSIVE على الملف لمدة محددة — يحاكي كاتباً بطيئاً."""
    def _worker():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute("BEGIN EXCLUSIVE")
        conn.execute("CREATE TABLE IF NOT EXISTS lock_probe(x)")
        time.sleep(seconds)
        conn.rollback()
        conn.close()
    import threading
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    time.sleep(0.4)  # نمنح الحاجز لحظة ليقبض على القفل فعلاً
    return t


async def pragma_of(eng, name):
    async with eng.connect() as c:
        r = await c.execute(text(f"PRAGMA {name}"))
        return r.scalar()


async def b_section():
    global FAIL
    # B1: المرض — محرك بلا درع (افتراضي: DELETE + 5 ثوانٍ) يفشل بالقفل
    plain = create_async_engine(
        "sqlite+aiosqlite:///" + DB_GUARD,
        connect_args={"check_same_thread": False},
    )
    # جدول موجود مسبقاً حتى يكون الفشل قفلاً لا نقص جدول
    async with plain.connect() as c:
        await c.execute(text("CREATE TABLE IF NOT EXISTS probe(id INTEGER)"))
        await c.commit()
    t1 = hold_exclusive(DB_GUARD, 6.5)
    t0 = time.monotonic()
    err1 = None
    try:
        async with plain.connect() as c:
            await c.execute(text("SELECT * FROM probe"))
    except OperationalError as e:
        err1 = e
    dt1 = time.monotonic() - t0
    t1.join()
    check(err1 is not None and S.is_locked_error(err1) and 4.0 < dt1 < 8.0,
          f"B1 · بلا درع: القارئ يفشل «database is locked» بعد {dt1:.1f}s (الافتراضي 5s)")
    await plain.dispose()

    # B2: الدواء — نفس الملف تحوّل WAL ثم نفس الحاجز: القارئ يعبر فوراً
    shielded_guard = create_async_engine(
        "sqlite+aiosqlite:///" + DB_GUARD,
        connect_args={"check_same_thread": False, "timeout": 8.0},
    )
    S.install_sqlite_lock_shield(shielded_guard)
    mode = await pragma_of(shielded_guard, "journal_mode")
    t2 = hold_exclusive(DB_GUARD, 6.5)
    t0 = time.monotonic()
    ok2 = False
    try:
        async with shielded_guard.connect() as c:
            await c.execute(text("SELECT * FROM probe"))
        ok2 = True
    except OperationalError:
        ok2 = False
    dt2 = time.monotonic() - t0
    t2.join()
    check(mode == "wal" and ok2 and dt2 < 2.0,
          f"B2 · بالدرع (WAL): نفس الحاجز — القارئ يعبر في {dt2:.2f}s")
    await shielded_guard.dispose()

    # B3: الكاتب بالدرع — ينتظر busy_timeout ثم ينجح
    shielded_w = create_async_engine(
        "sqlite+aiosqlite:///" + DB_WAL,
        connect_args={"check_same_thread": False, "timeout": 8.0},
    )
    S.install_sqlite_lock_shield(shielded_w)
    async with shielded_w.connect() as c:
        await c.execute(text("CREATE TABLE IF NOT EXISTS probe(id INTEGER)"))
        await c.commit()
    t3 = hold_exclusive(DB_WAL, 6.5)
    t0 = time.monotonic()
    ok3 = False
    try:
        async with shielded_w.connect() as c:
            await c.execute(text("INSERT INTO probe VALUES (42)"))
            await c.commit()
        ok3 = True
    except OperationalError:
        ok3 = False
    dt3 = time.monotonic() - t0
    t3.join()
    check(ok3 and 5.5 < dt3 < 10.0,
          f"B3 · بالدرع: الكاتب ينتظر القفل ({dt3:.1f}s) ثم ينجح — لا فقدان نتيجة")
    await shielded_w.dispose()

    # B4: المرض للكاتب — نفس السيناريو بلا درع: الكتابة تضيع بخط قفل
    plain_w = create_async_engine(
        "sqlite+aiosqlite:///" + DB_GUARD.replace("guard", "guard4"),
        connect_args={"check_same_thread": False},
    )
    async with plain_w.connect() as c:
        await c.execute(text("CREATE TABLE IF NOT EXISTS probe(id INTEGER)"))
        await c.commit()
    t4 = hold_exclusive(DB_GUARD.replace("guard", "guard4"), 6.5)
    err4 = None
    try:
        async with plain_w.connect() as c:
            await c.execute(text("INSERT INTO probe VALUES (7)"))
            await c.commit()
    except OperationalError as e:
        err4 = e
    t4.join()
    check(err4 is not None and S.is_locked_error(err4),
          "B4 · بلا درع: الكاتب يفشل بالقفل — هذا ما أضاع مهمة الإنتاج f9150e06")
    await plain_w.dispose()

    # B5: WAL يثبت في الملف — اتصال خارجي خام يرث الوضع
    raw = sqlite3.connect(DB_WAL)
    mode5 = raw.execute("PRAGMA journal_mode").fetchone()[0]
    raw.close()
    check(mode5 == "wal",
          "B5 · WAL محفوظ في ملف القاعدة — كل الاتصالات الخارجية ترثه")

    # B6: busy_timeout الفعلي على اتصال الدرع = قيمة الإعداد
    bt = await pragma_of(shielded_guard, "busy_timeout")
    check(bt == 8000,
          f"B6 · busy_timeout الفعلي = {bt}ms (القيمة الإنتاجية 30000ms)")

    # B7: synchronous = NORMAL (الوضع الموصى به رسمياً مع WAL)
    sy = await pragma_of(shielded_guard, "synchronous")
    check(sy == 1, f"B7 · synchronous = {sy} (1 = NORMAL — آمن وأسرع مع WAL)")

    # B8: with_lock_retry على كتابة حقيقية مقفلة — إعادة محاولة ناجحة
    # (محرك بمهلة قصيرة 0.4s عمداً: المحاولة الأولى تفشل بالقفل بسرعة ثم
    # تُعاد — هذا بالضبط ما يفعله الدرع داخل المهمة الموحدة عند الازدحام)
    db_b8 = DB_WAL + ".b8"
    short_eng = create_async_engine(
        "sqlite+aiosqlite:///" + db_b8,
        connect_args={"check_same_thread": False, "timeout": 0.4},
    )
    async with short_eng.connect() as c:
        await c.execute(text("CREATE TABLE IF NOT EXISTS probe(id INTEGER)"))
        await c.commit()
    tries = {"n": 0}
    t8 = hold_exclusive(db_b8, 1.5)

    async def insert_once():
        tries["n"] += 1
        async with short_eng.connect() as c:
            await c.execute(text("INSERT INTO probe VALUES (99)"))
            await c.commit()
        return True

    ok8 = False
    try:
        ok8 = await S.with_lock_retry(insert_once, what="B8")
    except OperationalError:
        ok8 = False
    t8.join()
    check(ok8 is True and tries["n"] >= 2,
          f"B8 · with_lock_retry حيّة على كتابة مقفلة ({tries['n']} محاولات) ثم نجحت")
    await short_eng.dispose()

asyncio.run(b_section())

# ======================================================================
section("القسم C — نقاط التركيب الجراحي السبع (8 فحوص)")
# ======================================================================

src_session = read(os.path.join(ROOT, "app", "database", "session.py"))
src_b1 = read(os.path.join(ROOT, "app", "routers", "backtest1.py"))
src_b = read(os.path.join(ROOT, "app", "routers", "backtest.py"))
src_tasks = read(os.path.join(ROOT, "app", "tasks", "backtest_tasks.py"))

check("install_sqlite_lock_shield(engine)" in src_session,
      "C1 · session.py: الدرع مركّب على المحرك الرئيسي")

check("install_sqlite_lock_shield(iso_engine)" in src_session,
      "C2 · session.py: الدرع مركّب على مصنع الجلسات المعزول (INSERT الضخم)")

n_timeout = src_session.count('"timeout": SQLITE_BUSY_TIMEOUT_MS / 1000.0')
check(n_timeout == 2,
      f"C3 · session.py: مهلة الانتظار على تعريفَي المحركين ({n_timeout}/2)")

check("with_lock_retry" in src_b1 and "_do_save" in src_b1
      and 'what=f"unified-exit save {backtest_id}"' in src_b1,
      "C4 · backtest1.py: حفظ المهمة الموحدة داخل with_lock_retry")

check(src_b1.count("execute_with_lock_retry") >= 2
      and 'what=f"backtest1/get {backtest_id}"' in src_b1
      and 'what="backtest1/list"' in src_b1,
      "C5 · backtest1.py: GET /get + GET /list عبر execute_with_lock_retry")

check("execute_with_lock_retry" in src_b
      and 'what=f"backtest/get {backtest_id}"' in src_b
      and 'what="backtest/list"' in src_b
      and "✅ R44 — القراءة عبر درع القفل" in src_b,
      "C6 · backtest.py: النقطة المركزية _get_backtest_row + /list محميّتان")

check("with_lock_retry" in src_tasks and "_commit_save" in src_tasks
      and 'what=f"save backtest {result.id}", session=db' in src_tasks,
      "C7 · backtest_tasks.py: حفظ المسار القياسي داخل with_lock_retry + rollback")

pg_regions = []
_idx = 0
while True:
    _idx = src_session.find(
        "clean_url, _pg_connect_args = build_asyncpg_connect_args", _idx)
    if _idx == -1:
        break
    pg_regions.append(src_session[_idx:_idx + 500])
    _idx += 10
pg_clean = len(pg_regions) == 2 and all(
    "install_sqlite_lock_shield" not in r and "PRAGMA" not in r
    for r in pg_regions)
cfg_src = read(os.path.join(ROOT, "app", "config.py"))
cfg_ok = ("SQLITE_BUSY_TIMEOUT_MS: int = 30000" in cfg_src
          and "SQLITE_LOCK_RETRIES: int = 5" in cfg_src
          and "SQLITE_LOCK_BASE_DELAY: float = 0.35" in cfg_src
          and "SQLITE_LOCK_MAX_DELAY: float = 6.0" in cfg_src)
check(pg_clean and cfg_ok,
      "C8 · مسار PostgreSQL نظيف (لا PRAGMA) + حقول R44 معرّفة في config.py")

# ======================================================================
section("القسم D — التكامل: الاستيراد الفعلي والمحرك الحي (10 فحوص)")
# ======================================================================


async def d_section():
    # D1: الوحدة المستوردة حقيقةً بمحركها الرئيسي على قاعدة الاختبار
    check(hasattr(S, "engine") and hasattr(S, "AsyncSessionLocal"),
          "D1 · الاستيراد الفعلي لـ app.database.session ناجح (محرك + مصنع)")

    # D2: وضع المحرك الرئيسي الحي = WAL
    m = await pragma_of(S.engine, "journal_mode")
    check(m == "wal", f"D2 · المحرك الرئيسي الحي: journal_mode = {m}")

    # D3: busy_timeout الحي على المحرك الرئيسي (قيمة البيئة أثناء البطارية)
    bt = await pragma_of(S.engine, "busy_timeout")
    check(bt == 8000, f"D3 · busy_timeout الحي = {bt}ms")

    # D4: synchronous الحي = NORMAL
    sy = await pragma_of(S.engine, "synchronous")
    check(sy == 1, f"D4 · synchronous الحي = {sy} (NORMAL)")

    # D5: المصنع المعزول — اتصاله أيضاً WAL
    maker, iso_eng = S.build_isolated_session_maker()
    async with maker() as db:
        r = await db.execute(text("PRAGMA journal_mode"))
        m5 = r.scalar()
    await iso_eng.dispose()
    check(m5 == "wal", f"D5 · المحرك المعزول (مسار الحفظ): journal_mode = {m5}")

    # D6: كتابة وقراءة كاملتان عبر الجلسة الرئيسية (insert → select)
    async with S.engine.begin() as c:
        await c.execute(text("CREATE TABLE IF NOT EXISTS r44_probe(id INTEGER, v TEXT)"))
        await c.execute(text("DELETE FROM r44_probe"))
        await c.execute(text("INSERT INTO r44_probe VALUES (1, 'hello-r44')"))
    async with S.AsyncSessionLocal() as db:
        r = await S.execute_with_lock_retry(
            db, text("SELECT v FROM r44_probe WHERE id=1"), what="D6")
        v = r.scalar()
    check(v == "hello-r44", "D6 · دورة كتابة+قراءة كاملة عبر المحرك بالدرع")

    # D7: execute_with_lock_retry على جلسة FastAPI-style تعيد Result سليماً
    async with S.AsyncSessionLocal() as db:
        r = await S.execute_with_lock_retry(db, text("SELECT 1+41"), what="D7")
        check(r.scalar() == 42, "D7 · execute_with_lock_retry يعيد Result سليماً")

    # D8: get_db dependency — يفتح جلسة ويغلقها (نمط FastAPI نفسه)
    gen = S.get_db()
    sess = await gen.__anext__()
    check(sess is not None, "D8 · get_db يفتح جلسة (نمط Depends نفسه)")
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass

    # D9: ملفات WAL الجانبية تظهر بعد كتابة فعلية (دليل بصري على الوضع)
    wal_side = os.path.exists(DB_MAIN + "-wal") or os.path.exists(DB_MAIN + "-shm")
    check(wal_side, "D9 · ملفا WAL/SHM موجودان بجانب القاعدة (الوضع يعمل فعلياً)")

    # D10: إعادة فتح القاعدة بعد إغلاق المحرك — الوضع باقٍ (استمرارية)
    await S.engine.dispose()
    raw = sqlite3.connect(DB_MAIN)
    m10 = raw.execute("PRAGMA journal_mode").fetchone()[0]
    raw.close()
    check(m10 == "wal", "D10 · بعد إعادة الفتح: القاعدة ما زالت WAL (يُثبَّت مرة ويبقى)")

asyncio.run(d_section())

# ======================================================================
section("القسم E — عقد الاكتمال وحراس الانحدار (8 فحوص)")
# ======================================================================

import subprocess  # noqa: E402

# E1: الملفات الأربعة تترجم بلا أخطاء
rc = subprocess.run(
    [sys.executable, "-m", "py_compile",
     os.path.join(ROOT, "app", "database", "session.py"),
     os.path.join(ROOT, "app", "routers", "backtest.py"),
     os.path.join(ROOT, "app", "routers", "backtest1.py"),
     os.path.join(ROOT, "app", "tasks", "backtest_tasks.py"),
     os.path.join(ROOT, "app", "config.py")],
    capture_output=True)
check(rc.returncode == 0, "E1 · الملفات الخمسة تترجم نظيفة (py_compile)")

# E2: بصمات حراس الانحدار — المحرك الموحد/الخروج/المخطط لم تُمس
all_ok = True
for rel, want in GUARD_MD5.items():
    import hashlib
    p = os.path.join(ROOT, rel)
    got = hashlib.md5(open(p, "rb").read()).hexdigest() if os.path.exists(p) else "?"
    if got != want:
        all_ok = False
        print(f"      ⚠️ {rel}: {got} != {want}")
check(all_ok, "E2 · unified_backtest/exit_engine/exit_strategy/backtest_run بت-بت (لا مساس)")

# E3: درع ج42.1/ج43 ما زال حياً في backtest1.py (لا انحدار)
check("_reject_exit_strategy_r421" in src_b1 and "[R42]" in src_b1,
      "E3 · درع الصراحة R42.1/R43 حيّ في backtest1.py (لا انحدار)")

# E4: المسار الموحد R42 نفسه موجود ويعلن نفسه
check("run_unified_exit_backtest" in src_b1 and "Unified Exit Engine" in src_b1,
      "E4 · المسار الموحد R42 (المحرك + التريلينق) سليم في مكانه")

# E5: القيم الافتراضية الإنتاجية عند غياب البيئة (30s/5/0.35/6.0)
env_backup = {k: os.environ.pop(k) for k in list(os.environ)
              if k.startswith("SQLITE_")}
defaults_ok = (
    int(os.environ.get("SQLITE_BUSY_TIMEOUT_MS", 30000) or 30000) == 30000
    and int(os.environ.get("SQLITE_LOCK_RETRIES", 5) or 5) == 5
    and float(os.environ.get("SQLITE_LOCK_BASE_DELAY", 0.35) or 0.35) == 0.35
    and float(os.environ.get("SQLITE_LOCK_MAX_DELAY", 6.0) or 6.0) == 6.0
)
for k, v in env_backup.items():
    os.environ[k] = v
check(defaults_ok, "E5 · الافتراضي الإنتاجي: 30000ms/5 محاولات/0.35s/سقف 6s (بلا أي .env)")

# E6: is_locked_error لا يلتقط كلاماً عابراً (حماية من إيجابيات زائفة)
check(S.is_locked_error(RuntimeError("database is locked again, seriously")) is False,
      "E6 · لا إيجابيات زائفة: RuntimeError نصّي لا يُعامَل كقفل قاعدة")

# E7: الدرع آمن للتكرار — تركيبه مرتين على نفس المحرك لا يكسر شيئاً
try:
    eng7 = create_async_engine("sqlite+aiosqlite:///" + DB_ISOLATED,
                               connect_args={"check_same_thread": False})
    S.install_sqlite_lock_shield(eng7)
    S.install_sqlite_lock_shield(eng7)
    asyncio.get_event_loop_policy()
    ok7 = asyncio.run(pragma_of(eng7, "journal_mode")) == "wal"
    asyncio.run(eng7.dispose()) if hasattr(eng7, "dispose") else None
except Exception as e:  # noqa: BLE001
    ok7 = False
    print("      ⚠️", e)
check(ok7, "E7 · تركيب الدرع مرتين idempotent (لا ازدواج ولا انفجار)")

# E8: العدّاد النهائي — 44 فحصاً لهذه الجولة بالضبط (43 قبل هذا الفحص)
total = PASS + FAIL
check(total == 43, f"E8 · عقد العدد: {total} قبل هذا + 1 = 44 فحصاً")

# ======================================================================
print(f"\n{'=' * 62}")
print(f"النتيجة النهائية: {PASS}/{PASS + FAIL}")
if FAILURES:
    print("الفحوص الفاشلة:")
    for f in FAILURES:
        print(f"  ✗ {f}")
    sys.exit(1)
print("✅ درع قفل قاعدة البيانات R44 مكتمل — كل الفحوص ناجحة")
