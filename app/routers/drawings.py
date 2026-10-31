# app/routers/drawings.py
"""✅ الجولة 4 — حفظ أدوات الرسم (Drawings) بشكل دائم.

نقاط REST لكل (market, symbol, timeframe):
- GET    /api/v1/chart/drawings/{market}/{symbol}?timeframe=1m  → قائمة الأدوات
- POST   /api/v1/chart/drawings/{market}/{symbol}               → استبدال/حفظ دفعة كاملة
- DELETE /api/v1/chart/drawings/{market}/{symbol}?timeframe=1m  → مسح (فريم محدد أو الكل)

التخزين: SQLite (chart_drawings.db) — يبقى بعد إعادة التشغيل. الشكل حر (JSON
شفاف) — الفرونت يرسل أدواته كما هي (خط اتجاه/مستطيل/نص/فيبوناتشي...) والخادم
يخزنها ويعيدها كما وردت، مع معرف وترتيب محفوظ.
"""

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.storage_health import ensure_sqlite_ready

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chart-drawings"])

# ✅ الجولة 6: مسار قابل للضبط بالبيئة + تجهيز ذاتي (مجلد/صلاحيات/أثر Docker).
# كان الإنتاج فاشلاً بـ "unable to open database file" لأن ربط ملف واحد في
# docker-compose أنشأ directory فارغاً بدل الملف — يُصلح ذاتياً الآن، ويمكن
# ضبط المسار الصريح عبر DRAWINGS_DB_PATH (يضبطه docker-compose المحدّث).
_RAW_DB_PATH = os.environ.get("DRAWINGS_DB_PATH", "chart_drawings.db")
_DB_PATH = ensure_sqlite_ready(_RAW_DB_PATH, label="chart_drawings")


def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drawings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope_key TEXT NOT NULL,          -- "market|SYMBOL|timeframe"
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            payload TEXT NOT NULL,            -- JSON: قائمة الأدوات كما أرسلها الفرونت
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope_key)
        )
        """
    )
    return conn


def _conn() -> sqlite3.Connection:
    """فتح قاعدة الأدوات — وعند فشل تشغيلي (مسار/صلاحيات) نُعيد التجهيز الذاتي
    مرة واحدة ثم نحاول مجدداً (يُصلح حالة أُصلحت صلاحياتها بعد الإقلاع)."""
    global _DB_PATH
    try:
        return _open_conn()
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "unable to open" in msg or "readonly" in msg or "locked" in msg:
            logger.warning("🩹 فشل فتح قاعدة الأدوات (%s) — إعادة تجهيز ذاتي للمسار...", exc)
            _DB_PATH = ensure_sqlite_ready(_RAW_DB_PATH, label="chart_drawings", force=True)
            return _open_conn()
        raise


class DrawingsSaveRequest(BaseModel):
    """دفعة أدوات الرسم — تُحفظ كاملة كبديل لما هو مخزن (upsert بمفتاح scope)."""
    timeframe: str = Field("1m", description="الفريم الزمني — أو 'all' لتخزين عالمي للرمز")
    drawings: List[Dict[str, Any]] = Field(
        default_factory=list,
        description='قائمة الأدوات بشكل حر: [{"type":"trend_line","points":[...],"style":{...}}, ...]')


def _scope(market: str, symbol: str, timeframe: str) -> str:
    return f"{market.lower()}|{symbol.upper()}|{timeframe}"


@router.get(
    "/drawings/{market}/{symbol}",
    summary="✅ الجولة 4: جلب أدوات الرسم المحفوظة لرمز×فريم",
)
async def get_drawings(
    market: str,
    symbol: str,
    timeframe: str = Query("1m", description="الفريم الزمني — أو all لكل الفريمات"),
):
    try:
        conn = _conn()
        try:
            if timeframe.lower() == "all":
                rows = conn.execute(
                    "SELECT timeframe, payload, updated_at FROM drawings "
                    "WHERE market = ? AND symbol = ? ORDER BY updated_at DESC",
                    (market.lower(), symbol.upper()),
                ).fetchall()
                drawings_map = {}
                for tf, payload, updated in rows:
                    try:
                        drawings_map[tf] = {
                            "drawings": json.loads(payload),
                            "updated_at": updated,
                        }
                    except Exception:  # noqa: BLE001
                        continue
                return {
                    "market": market.lower(),
                    "symbol": symbol.upper(),
                    "timeframes": drawings_map,
                    "count": sum(len(v["drawings"]) for v in drawings_map.values()),
                }
            row = conn.execute(
                "SELECT payload, updated_at FROM drawings WHERE scope_key = ?",
                (_scope(market, symbol, timeframe),),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return {"market": market.lower(), "symbol": symbol.upper(),
                    "timeframe": timeframe, "drawings": [], "count": 0}
        return {
            "market": market.lower(),
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "drawings": json.loads(row[0]),
            "count": len(json.loads(row[0])),
            "updated_at": row[1],
        }
    except Exception:
        logger.exception("Failed to load drawings for %s/%s", market, symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/drawings/{market}/{symbol}",
    summary="✅ الجولة 4: حفظ أدوات الرسم (upsert كامل للدفعة)",
)
async def save_drawings(
    market: str,
    symbol: str,
    req: DrawingsSaveRequest = Body(...),
):
    try:
        scope = _scope(market, symbol, req.timeframe)
        payload = json.dumps(req.drawings, ensure_ascii=False, default=str)
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT INTO drawings (scope_key, market, symbol, timeframe, payload, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(scope_key) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (scope, market.lower(), symbol.upper(), req.timeframe, payload),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "success": True,
            "market": market.lower(),
            "symbol": symbol.upper(),
            "timeframe": req.timeframe,
            "saved": len(req.drawings),
        }
    except Exception:
        logger.exception("Failed to save drawings for %s/%s", market, symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete(
    "/drawings/{market}/{symbol}",
    summary="✅ الجولة 4: مسح أدوات الرسم — وأصبح يدعم الحذف الدفعي بالمعرفات (الجولة 6)",
)
async def delete_drawings(
    market: str,
    symbol: str,
    timeframe: str = Query(None, description="احذف فريماً محدداً — أو اتركه لحذف الكل"),
    drawing_id: Optional[str] = Query(None, description="حذف أداة واحدة بالمعرف داخل القائمة"),
    drawing_ids: Optional[List[str]] = Query(
        None,
        description=(
            "✅ الجولة 6: حذف دفعي — معرفات مفصولة بفواصل (?drawing_ids=a,b,c) "
            "أو بتكرار المعامل (?drawing_ids=a&drawing_ids=b). "
            "مع timeframe: يُطبق على ذلك الفريم فقط؛ بدونه: يُطبق على كل فريمات الرمز "
            "(مثالي لزر مسح الكل). الاستجابة: success + deleted (العدد) + deleted_ids/not_found."
        ),
    ),
):
    try:
        # توحيد المعرفات: نقبل "a,b,c" أو تكرار المعامل — وننزع الفراغات والتكرار
        ids: List[str] = []
        for entry in (drawing_ids or []):
            ids.extend(p.strip() for p in str(entry).split(",") if p.strip())
        ids = list(dict.fromkeys(ids))
        id_set = set(ids)

        conn = _conn()
        try:
            # ---------- ✅ الجولة 6: الحذف الدفعي ----------
            if id_set:
                if timeframe:
                    scopes = [_scope(market, symbol, timeframe)]
                else:
                    rows = conn.execute(
                        "SELECT scope_key, payload FROM drawings "
                        "WHERE market = ? AND symbol = ?",
                        (market.lower(), symbol.upper()),
                    ).fetchall()
                    scopes = [r[0] for r in rows]

                total_deleted = 0
                deleted_ids: List[str] = []
                not_found = list(ids)
                affected: List[str] = []
                for scope in scopes:
                    row = conn.execute(
                        "SELECT payload FROM drawings WHERE scope_key = ?", (scope,)
                    ).fetchone()
                    if not row:
                        continue
                    try:
                        items = json.loads(row[0])
                    except Exception:  # noqa: BLE001
                        continue
                    kept = [d for d in items if str(d.get("id", "")) not in id_set]
                    removed = len(items) - len(kept)
                    if not removed:
                        continue
                    removed_ids = [
                        str(d.get("id", "")) for d in items
                        if str(d.get("id", "")) in id_set
                    ]
                    if kept:
                        conn.execute(
                            "UPDATE drawings SET payload = ?, updated_at = CURRENT_TIMESTAMP "
                            "WHERE scope_key = ?",
                            (json.dumps(kept, ensure_ascii=False, default=str), scope),
                        )
                    else:
                        # القائمة أصبحت فارغة — نحذف الصف كلياً (يُرجع GET count=0 كما هو)
                        conn.execute("DELETE FROM drawings WHERE scope_key = ?", (scope,))
                    total_deleted += removed
                    deleted_ids.extend(removed_ids)
                    # scope_key = "market|SYMBOL|timeframe" → نُرجع الفريم فقط
                    affected.append(scope.split("|")[-1])
                conn.commit()
                not_found = [i for i in ids if i not in set(deleted_ids)]
                return {
                    "success": True,
                    "deleted": total_deleted,
                    "deleted_ids": deleted_ids,
                    "not_found": not_found,
                    "timeframes_affected": sorted(set(affected)),
                }

            # ---------- السلوك الأصلي (توافق قديم كامل) ----------
            if timeframe:
                if drawing_id:
                    row = conn.execute(
                        "SELECT payload FROM drawings WHERE scope_key = ?",
                        (_scope(market, symbol, timeframe),),
                    ).fetchone()
                    if not row:
                        return {"success": True, "deleted": 0}
                    items = json.loads(row[0])
                    kept = [d for d in items if str(d.get("id", "")) != drawing_id]
                    conn.execute(
                        "UPDATE drawings SET payload = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE scope_key = ?",
                        (json.dumps(kept, ensure_ascii=False, default=str),
                         _scope(market, symbol, timeframe)),
                    )
                    conn.commit()
                    return {"success": True, "deleted": len(items) - len(kept)}
                cur = conn.execute(
                    "DELETE FROM drawings WHERE scope_key = ?",
                    (_scope(market, symbol, timeframe),),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM drawings WHERE market = ? AND symbol = ?",
                    (market.lower(), symbol.upper()),
                )
            conn.commit()
            return {"success": True, "deleted": cur.rowcount}
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to delete drawings for %s/%s", market, symbol)
        raise HTTPException(status_code=500, detail="Internal server error")
