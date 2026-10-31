# app/core/storage_health.py
"""
الجولة 6 — صحة تخزين SQLite: تشخيص ذاتي + إصلاح ذاتي (Self-Healing Storage).

المشاكل التي كانت تُسقط الإنتاج (دليل السجلات 2026-10-30):
1) `sqlite3.OperationalError: unable to open database file` — السبب: ربط ملف واحد
   في docker-compose (`./chart_drawings.db:/app/chart_drawings.db`) حيث إذا لم
   يكن الملف موجوداً على المضيف يُنشئه Docker **ك directory فارغ** — وSQLite لا
   يفتح directory أبداً. كان يفشل حتى GET للأدوات المحفوظة.
2) `attempt to write a readonly database` — السبب: نفس الربط لملف `chart_states.db`
   المملوك لـ root على المضيف بينما الحاوية تعمل بمستخدم trader (uid 1000):
   الفتح ينجح (قراءة) وأي كتابة/إنشاء journal يفشل.

الحل هنا (ثلاث طبقات دفاع):
- الطبقة 1: التأكد من وجود المسار وإنشاء مجلده قبل الفتح.
- الطبقة 2: كشف "directory بدل ملف" (أثر Docker) وإزالته إن كان فارغاً.
- الطبقة 3: فحص الكتابة فعلياً (probe) — وإن فشل: محاولة chmod ثم الانتقال
  تلقائياً لمسار بديل قابل للكتابة مع **نسخ البيانات القديمة** إن كانت مقروءة
  (لا فقدان بيانات) — مع سجل صريح يوضح السبب وأمر الإصلاح النهائي على الخادم.

كل قاعدة SQLite في المشروع تمر عبر ensure_sqlite_ready() — ونقطة
`GET /health/storage` تعيد تقريراً حياً بالمسارات والصلاحيات (إثبات request/response).
"""
import hashlib
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# كولداون إعادة الفحص بعد فشل أولي — يمنع ضرب القرص في كل طلب
_RECHECK_COOLDOWN = 60.0

# سجل الحالة لكل قاعدة مسجلة: label -> dict
_REGISTRY: Dict[str, Dict[str, Any]] = {}


# ----------------------------------------------------------------------------
# أدوات داخلية
# ----------------------------------------------------------------------------
def _absolutize(path: str) -> Path:
    """مسار مطلق — المسارات النسبية تُقيّد على CWD وقت الاستيراد، وهشاشة نتجنبها."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _probe_writable(db_path: Path) -> Optional[str]:
    """فحص كتابة حقيقي على القاعدة نفسها. يُعيد None إذا كانت قابلة للكتابة،
    وإلا سطر السبب (نفس رسالة الإنتاج حرفياً عند المشكلة)."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS _storage_probe (k INTEGER)")
            conn.execute("INSERT INTO _storage_probe (k) VALUES (1)")
            conn.execute("DELETE FROM _storage_probe")
            conn.commit()
        finally:
            conn.close()
        return None
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def _fallback_dirs(original: Path) -> List[Path]:
    """مجلدات مرشحة لمسار بديل قابل للكتابة — بالترتيب:
    1) STORAGE_FALLBACK_DIR من البيئة (تحكم صريح من المشغل)
    2) /app/data — طبقة الحاوية القابلة للكتابة (يمتلكها trader في صورة الإنتاج)
    3) ./data بجوار CWD
    4) مجلد النظام المؤقت — ملاذ أخير (يعمل دائماً لكنه مؤقت على إعادة البناء)
    """
    cands: List[Path] = []
    env_dir = os.environ.get("STORAGE_FALLBACK_DIR")
    if env_dir:
        cands.append(_absolutize(env_dir))
    cands.append(Path("/app/data"))
    cands.append(Path.cwd() / "data")
    cands.append(Path(tempfile.gettempdir()))
    # لا نرشح مجلد القاعدة الأصلي نفسه (هو سبب الفشل غالباً)
    return [c for c in cands if c.resolve() != original.parent.resolve()]


def _docker_fix_hint(label: str) -> str:
    return (
        f"إصلاح جذري على الخادم: استخدم docker-compose المحدّث (حجم مسمى chart_data "
        f"بدل ربط ملف واحد) — أو مؤقتاً: docker compose exec -u root backend sh -c "
        f"'chown -R trader:trader /app && chmod -R u+rw /app' ثم أعد الحاوية. "
        f"[label={label}]"
    )


# ----------------------------------------------------------------------------
# الواجهة الرئيسية
# ----------------------------------------------------------------------------
def ensure_sqlite_ready(path: str, label: str = "sqlite", force: bool = False) -> str:
    """يضمن مسار SQLite صالحاً وقابلاً للكتابة — ويعيد المسار النهائي المستخدم.

    يستدعى مرة عند تحميل الوحدة (سريع بلا فحص ثقيل بعد أول نجاح)، وقابل
    للاستدعاء القسري force=True عند فشل تشغيلي (مع كولداون 60 ثانية).

    🩹 إصلاحات ذاتية منفذة هنا:
    - مجلد القاعدة غير موجود → إنشاؤه.
    - المسار directory فارغ (أثر Docker لأجل ربط ملف واحد) → إزالته واستخدام ملف.
    - ملف غير قابل للكتابة → محاولة chmod ثم مسار بديل مع نسخ البيانات المقروءة.
    """
    reg = _REGISTRY.get(label)
    abs_path = _absolutize(path)
    same_input = reg is not None and reg.get("requested") == str(abs_path)

    # مسار سريع: نجاح سابق على نفس المدخل — بلا فحص جديد
    if same_input and not force and reg.get("ok"):
        return str(reg["resolved"])

    # كولداون: فشل مؤخراً؟ لا تُرهق القرص إلا بعد 60 ثانية
    if same_input and not force and not reg.get("ok") \
            and (time.monotonic() - float(reg.get("checked_at", 0))) < _RECHECK_COOLDOWN:
        return str(reg["resolved"])

    status: Dict[str, Any] = {
        "label": label,
        "requested": str(abs_path),
        "resolved": str(abs_path),
        "ok": False,
        "is_file": False,
        "is_dir": False,
        "writable": False,
        "fallback_active": False,
        "last_error": None,
        "checked_at": time.monotonic(),
    }

    final = abs_path
    try:
        # --- الطبقة 1: مجلد الحاوية ---
        try:
            final.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            status["last_error"] = f"mkdir({final.parent}) failed: {e}"

        # --- الطبقة 2: أثر Docker — directory بدل ملف ---
        if final.is_dir():
            status["is_dir"] = True
            empty = next(iter(final.iterdir()), None) is None
            if empty:
                try:
                    os.rmdir(final)
                    logger.warning(
                        "🩹 [%s] أُزيل directory فارغ بدل ملف القاعدة (أثر ربط ملف واحد في Docker): %s",
                        label, final)
                    status["is_dir"] = False
                except Exception as e:  # noqa: BLE001
                    status["last_error"] = f"is-a-directory (not removable): {e}"
            else:
                status["last_error"] = "path is a non-empty directory"

        # --- الطبقة 3: فحص كتابة فعلي ---
        reason = _probe_writable(final)
        if reason and final.exists() and final.is_file():
            # محاولة chmod (تنجح إن كنا مالكي الملف — تصلح حالة "أُنشئ بلا صلاحية كتابة")
            try:
                os.chmod(final, 0o664)
                reason = _probe_writable(final)
                if reason is None:
                    logger.warning("🩹 [%s] أُصلحت صلاحيات الملف بـ chmod 664: %s", label, final)
            except Exception:  # noqa: BLE001
                pass

        if reason is None:
            status["ok"] = True
            status["writable"] = True
        else:
            status["last_error"] = reason
            # --- المسار البديل: نسخة قابلة للكتابة مع الحفاظ على البيانات ---
            for cand in _fallback_dirs(final):
                try:
                    cand.mkdir(parents=True, exist_ok=True)
                except Exception:  # noqa: BLE001
                    continue
                # لاحقة ثابتة مشتقة من المسار الأصلي: تمنع تداخل قاعدتين تحملان
                # الاسم نفسه، وتبقى مستقرة عبر إعادة التشغيل (نفس المسار → نفس الاسم).
                tag = hashlib.md5(str(final).encode()).hexdigest()[:6]
                fb = cand / f"{final.stem}.writable-{tag}{final.suffix or '.db'}"
                if not (fb.is_file() and _probe_writable(fb) is None):
                    try:
                        fb.unlink(missing_ok=True)
                    except Exception:  # noqa: BLE001
                        pass
                    copied = False
                    if final.is_file():
                        try:
                            shutil.copy2(final, fb)
                            copied = True
                        except Exception as e:  # noqa: BLE001
                            logger.warning(
                                "⚠️ [%s] تعذر نسخ القاعدة القديمة (%s) — سيُنشأ ملف جديد", label, e)
                    if _probe_writable(fb) is not None:
                        continue  # المرشح التالي
                    logger.warning(
                        "🩹 [%s] انتقل التخزين لمسار بديل قابل للكتابة: %s (نسخ البيانات القديمة: %s) — السبب: %s",
                        label, fb, "نعم" if copied else "لا", reason)
                status["fallback_active"] = True
                final = fb
                status["ok"] = True
                status["writable"] = True
                status["resolved"] = str(fb)
                break
    except Exception as e:  # noqa: BLE001 — لا نُسقط التطبيق أبداً بسبب التشخيص
        status["last_error"] = f"unexpected: {type(e).__name__}: {e}"
        logger.exception("❌ [%s] فشل غير متوقع في تجهيز التخزين", label)

    status["is_file"] = final.is_file() and not final.is_dir()
    if status["ok"]:
        logger.info("✅ SQLite storage ready [%s] → %s%s", label, final,
                    " (fallback)" if status["fallback_active"] else "")
    else:
        logger.error("❌ SQLite storage NOT writable [%s] → %s — السبب: %s — %s",
                     label, final, status["last_error"], _docker_fix_hint(label))
    _REGISTRY[label] = status
    return str(final)


def register(label: str, requested: str, resolved: str, ok: bool,
             fallback_active: bool = False, error: Optional[str] = None) -> None:
    """تسجيل حالة من الوحدات التي تدير مسارها بنفسها (للتقرير الموحد فقط)."""
    _REGISTRY[label] = {
        "label": label,
        "requested": requested,
        "resolved": resolved,
        "ok": ok,
        "writable": ok,
        "is_file": Path(resolved).is_file(),
        "is_dir": Path(resolved).is_dir(),
        "fallback_active": fallback_active,
        "last_error": error,
        "checked_at": time.monotonic(),
    }


def storage_status() -> Dict[str, Any]:
    """تقرير حي لكل قواعد SQLite المسجلة — يستخدمه GET /health/storage."""
    dbs: List[Dict[str, Any]] = []
    for label, st in _REGISTRY.items():
        resolved = Path(st.get("resolved", ""))
        live = dict(st)
        if resolved and str(resolved) != ".":
            live["exists"] = resolved.exists()
            live["is_file"] = resolved.is_file()
            live["is_dir"] = resolved.is_dir()
            live["writable"] = _probe_writable(resolved) is None
            try:
                stt = resolved.stat()
                live["size_bytes"] = stt.st_size
                live["owner_uid"] = stt.st_uid
            except Exception:  # noqa: BLE001
                pass
        dbs.append(live)
    try:
        import pwd  # noqa: WPS433 — متاح على لينكس/الإنتاج
        user = pwd.getpwuid(os.geteuid()).pw_name
    except Exception:  # noqa: BLE001
        user = str(os.geteuid())
    return {
        "process": {
            "pid": os.getpid(),
            "euid": os.geteuid(),
            "egid": os.getgid(),
            "user": user,
            "cwd": os.getcwd(),
        },
        "databases": dbs,
    }


def log_storage_report() -> None:
    """سطر تلخيصي عند الإقلاع — يظهر في docker logs مباشرة."""
    st = storage_status()
    proc = st["process"]
    for db in st["databases"]:
        state = "✅" if db.get("ok") else "❌"
        logger.info("%s Storage[%s] → %s (writable=%s, fallback=%s, error=%s)",
                    state, db.get("label"), db.get("resolved"),
                    db.get("writable"), db.get("fallback_active"), db.get("last_error"))
    logger.info("🔎 Storage process context: user=%s euid=%s cwd=%s",
                proc["user"], proc["euid"], proc["cwd"])
