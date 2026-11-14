#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
✅ PRO73 Control Service — خدمة التحكم الخلفية للمحركين «ترنديه ماكديه»
و«ملتهبه ماكديه» (منفذ ثابت 8730 — stdlib بلا أي اعتماد خارجي).

المسارات (كلها JSON):
  GET  /api/ping                  → نبض الخدمة + إصدارات النواة/المكتبة
  GET  /api/catalog               → الفريمات الـ14 + أنواع الموشرات + نسخ
                                     المستند الـ67 + فهرس الحالات الـ19
                                     (13 حالة + 6 وحدات ماكرو) + المحركات
  GET  /api/state                 → الحالة المحفوظة (أو الافتراضية)
  POST /api/state                 → حفظ الحالة (مع تحذيرات التطبيع)
  POST /api/reset                 → إرجاع الحالة للافتراضية (المستند الكامل)
  GET  /api/data/range            → مدى بيانات SOLUSDT 1m
  POST /api/compute               → تشغيل المحرك المختار على نافذة:
                                     الشموع + سلاسل النسخ + البوابة + الشفافية
                                     الرباعية + إصابات كل حالة + فلترة الهابط
  POST /api/cases                 → تقييم الحالات الثلاث عشرة فقط على نافذة
  POST /api/backtest              → باك-تست عبر المسار الإنتاجي نفسه
                                     (StrategyEngine → ind_zzfetm_*/ind_zzfbm_*)
                                     مع مفتاح A/B (هوية = بلا بوابة)

حدود النوافذ (ذاكرة الجهاز 3GB): ≤ 75 يوماً للنوافذ التفاعلية — نافذة البطل
الكاملة (462 يوماً) تُشغَّل عبر سكربت التحقق خارج الخدمة.
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import math
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/home/z/my-project/pro73-workspace/src"
if SRC not in sys.path:
    sys.path.insert(0, SRC)

PORT = 8730
STATE_FILE = os.path.join(HERE, "state.json")
DATA_PATH = "/home/z/my-project/r70-workspace/data/SOLUSDT_1m.npz"
MAX_WINDOW_DAYS = 75          # حد النوافذ التفاعلية (ذاكرة الجهاز)
MAX_POINTS_DEFAULT = 800      # عدد نقاط الشارت المعادة (تنازلي مع الحفاظ على آخر شمعة)
MAX_TRADES_RETURNED = 200

os.environ.setdefault("SECRET_KEY", "pro73-control-local-secret-key")
os.environ.setdefault("DEBUG", "true")

import numpy as np  # noqa: E402

from app.services.indicators.mtf_oscillator_core import (  # noqa: E402
    MTF_OSC_CORE_VERSION, TF_ORDER, TF_REGISTRY, OSC_KIND_FIELDS,
    compute_oscillator_matrix, evaluate_osc_conditions,
    normalize_osc_instances, normalize_osc_conditions,
)
from app.services.indicators.osc_cases import (  # noqa: E402
    OSC_DOC_INSTANCES, OSC_CASE_LIBRARY, OSC_CASE_CATALOG,
    OSC_DOC_URL, OSC_DOC_SOURCE,
    OSC_CASE_LIBRARY_SPEC, OSC_CASE_LIBRARY_VERSION,
)
from app.services.indicators.overlays_zlf_e2e_trendy_macd import (  # noqa: E402
    zigzag_fib_e2e_trendy_macd, ZLF_E2E_TRENDY_MACD_SPEC,
)
from app.services.indicators.overlays_zlf_e2e_blazing_macd import (  # noqa: E402
    zigzag_fib_e2e_blazing_macd, ZLF_E2E_BLAZING_MACD_SPEC,
)

SERVICE_VERSION = "1.0.0"
SERVICE_SPEC = "PRO73-control"

_LOCK = threading.RLock()
_DATA: dict = {}


# ---------------------------------------------------------------------------
# أدوات عامة
# ---------------------------------------------------------------------------
def _j(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")


def _iso(ms: int) -> str:
    try:
        return _dt.datetime.fromtimestamp(int(ms) / 1000.0, _dt.timezone.utc).isoformat()
    except Exception:
        return str(ms)


def _to_ms(v) -> int:
    """'2023-09-01' | '2023-09-01T00:00:00Z' | epoch-ms → ms (UTC)."""
    if v is None:
        raise ValueError("قيمة زمنية مفقودة")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
        return int(f * 1000.0) if f < 1e11 else int(f)
    s = str(v).strip()
    try:
        f = float(s)
        return _to_ms(f)
    except ValueError:
        pass
    s2 = s.replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s2)
    except ValueError as exc:
        raise ValueError(f"صيغة زمن غير مفهومة: '{v}'") from exc
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return int(d.timestamp() * 1000)


def _round(v, nd: int = 6):
    try:
        f = float(v)
        if not math.isfinite(f):
            return None
        r = round(f, nd)
        return int(r) if r == int(r) else r
    except Exception:
        return None


def _stride_idx(n: int, max_pts: int):
    if n <= 0:
        return []
    if n <= max_pts:
        return list(range(n))
    step = int(math.ceil(n / max_pts))
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def _np_of(vals, n: int) -> np.ndarray:
    arr = np.asarray([np.nan if x is None else float(x) for x in (vals or [])], dtype=np.float64)
    if len(arr) < n:
        arr = np.concatenate((arr, np.full(n - len(arr), np.nan)))
    return arr[:n]


# ---------------------------------------------------------------------------
# الحالة الافتراضية/المحفوظة
# ---------------------------------------------------------------------------
def _default_state() -> dict:
    return {
        "version": 1,
        "engine": "trendy_macdized",           # trendy_macdized | blazing_macdized
        "symbol": "SOLUSDT",
        "base_tf": "1m",
        "window": {"from": "2023-09-01", "to": "2023-11-07"},
        "trend": {
            "mode": "luxalgo", "length": 100,
            "trend_periods": [7, 15, 25], "trend_confirm": "majority",
            "trend_gate": ["s1", "s2", "s3"],
        },
        "osc_instances": copy.deepcopy(OSC_DOC_INSTANCES),
        "osc_conditions": copy.deepcopy(OSC_CASE_CATALOG[-4]["tree"]),  # master_any_case
    }


def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            st = json.load(fh)
        if isinstance(st, dict) and "osc_instances" in st:
            return st
    except Exception:
        pass
    st = _default_state()
    _save_state_raw(st)
    return st


def _save_state_raw(st: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1, default=str)


def _validate_state(st: dict) -> list:
    insts, w1 = normalize_osc_instances(st.get("osc_instances"))
    tree, w2 = normalize_osc_conditions(st.get("osc_conditions"))
    warns = list(w1) + list(w2)
    if not insts:
        warns.append("لا نسخ موشرات في الحالة — البوابة ستكون تمريراً كاملاً (هوية)")
    return warns


# ---------------------------------------------------------------------------
# البيانات (SOLUSDT 1m — تحميل مرة واحدة)
# ---------------------------------------------------------------------------
def _data():
    with _LOCK:
        if _DATA:
            return _DATA
        z = np.load(DATA_PATH)
        t = z["time_ms"].astype(np.int64)
        _DATA["t"] = t
        _DATA["o"] = z["open"].astype(np.float64)
        _DATA["h"] = z["high"].astype(np.float64)
        _DATA["l"] = z["low"].astype(np.float64)
        _DATA["c"] = z["close"].astype(np.float64)
        _DATA["v"] = z["volume"].astype(np.float64)
        _DATA["first"] = int(t[0])
        _DATA["last"] = int(t[-1])
        return _DATA


def _load_window(from_ms: int, to_ms: int) -> dict:
    d = _data()
    if to_ms <= from_ms:
        raise ValueError("النافذة فارغة (to ≤ from)")
    days = (to_ms - from_ms) / 86_400_000.0
    if days > MAX_WINDOW_DAYS:
        raise ValueError(
            f"النافذة {days:.1f} يوماً تتجاوز الحد التفاعلي {MAX_WINDOW_DAYS} يوماً "
            f"(ذاكرة الجهاز) — استخدم نافذة أصغر؛ نافذة البطل الكاملة تُتحقق عبر سكربت التحقق"
        )
    m = (d["t"] >= from_ms) & (d["t"] < to_ms)
    n = int(m.sum())
    if n < 500:
        raise ValueError(f"شموع قليلة جداً في النافذة ({n}) — وسّع النطاق")
    T = d["t"][m]
    O = d["o"][m]
    H = d["h"][m]
    L = d["l"][m]
    C = d["c"][m]
    V = d["v"][m]
    return {
        "t": T, "o": O, "h": H, "l": L, "c": C, "v": V,
        "candles": [
            {"time": int(T[i]), "open": float(O[i]), "high": float(H[i]),
             "low": float(L[i]), "close": float(C[i]), "volume": float(V[i])}
            for i in range(n)
        ],
        "bars": n,
    }


# ---------------------------------------------------------------------------
# المحركات
# ---------------------------------------------------------------------------
def _engine_fn(engine_id: str):
    if engine_id == "trendy_macdized":
        return zigzag_fib_e2e_trendy_macd
    if engine_id == "blazing_macdized":
        return zigzag_fib_e2e_blazing_macd
    raise ValueError(f"محرك غير معروف: '{engine_id}' (trendy_macdized | blazing_macdized)")


def _engine_series_prefix(engine_id: str) -> str:
    return "zzfetm_" if engine_id == "trendy_macdized" else "zzfbm_"


_KINDS = {
    "trendy_macdized": ["s1", "s2", "s3"],
    "blazing_macdized": ["s1", "s2", "s3", "n5", "n6"],
}


def _run_engine(st: dict, win: dict, instances, conditions) -> dict:
    trend = st.get("trend") or {}
    fn = _engine_fn(st.get("engine") or "trendy_macdized")
    t0 = time.perf_counter()
    res = fn(
        win["candles"],
        length=int(trend.get("length", 100)),
        mode=str(trend.get("mode", "luxalgo")),
        trend_periods=trend.get("trend_periods", [7, 15, 25]),
        trend_confirm=trend.get("trend_confirm", "majority"),
        trend_gate=trend.get("trend_gate"),
        osc_instances=instances,
        osc_conditions=conditions,
    )
    res["_elapsed_s"] = round(time.perf_counter() - t0, 2)
    return res


def _col(res: dict, name: str, n: int):
    v = (res.get("series") or {}).get(name) or []
    out = [float(x) if x is not None else 0.0 for x in v]
    if len(out) < n:
        out = out + [0.0] * (n - len(out))
    return out[:n]


def _case_hits_from_series(res: dict, prefix: str, win: dict) -> dict:
    """إصابات الحالات الـ13 من سلاسل المحرك نفسه (بلا إعادة حساب)."""
    n = win["bars"]
    t = win["t"]
    osc_np: dict = {}
    for key, vals in (res.get("series") or {}).items():
        k = str(key)
        tag = f"{prefix}osc_"
        if not k.startswith(tag):
            continue
        rest = k[len(tag):]
        if "_" not in rest:
            continue
        iid, field = rest.rsplit("_", 1)
        osc_np.setdefault(iid, {})[field] = _np_of(vals, n)
    avail = {str(rep.get("id")): bool(rep.get("available", True))
             for rep in ((res.get("osc") or {}).get("instances") or [])}
    o = np.asarray(win["o"], dtype=np.float64)
    h = np.asarray(win["h"], dtype=np.float64)
    l = np.asarray(win["l"], dtype=np.float64)
    c = np.asarray(win["c"], dtype=np.float64)
    out = {}
    for case in OSC_CASE_LIBRARY:
        tree, _ = normalize_osc_conditions(case["tree"])
        g, _ = evaluate_osc_conditions(tree, osc_np, o, h, l, c, n, osc_available=avail)
        hits = int(g.sum())
        entry = {
            "id": case["id"], "family": case["family"], "kind": case["kind"],
            "title": case["title"], "hits": hits,
            "pct_of_bars": round(hits / n * 100.0, 3) if n else 0.0,
        }
        if hits:
            w = np.nonzero(g)[0]
            entry["first"] = {"bar": int(w[0]), "t": int(t[w[0]]), "iso": _iso(t[w[0]])}
            entry["last"] = {"bar": int(w[-1]), "t": int(t[w[-1]]), "iso": _iso(t[w[-1]])}
            entry["samples"] = [{"bar": int(b), "t": int(t[b]), "iso": _iso(t[b])} for b in w[:5]]
        out[case["id"]] = entry
    return out


def _regime_stats(res: dict, prefix: str, kinds: list, win: dict) -> dict:
    """فلترة المناطق الهابطة (نموذج البطارية E): 1h SMA50/200 بلا نظرة مستقبلية."""
    n = win["bars"]
    t = win["t"]
    # تجميع 1h
    hr = 3_600_000
    keys = t // hr
    starts = np.concatenate(([0], np.nonzero(np.diff(keys))[0] + 1)) if n else np.zeros(0, dtype=int)
    closes_1h = win["c"][starts] if len(starts) else np.zeros(0)
    hour_keys = keys[starts] if len(starts) else np.zeros(0, dtype=np.int64)
    closes = np.asarray(closes_1h, dtype=np.float64)

    def _sma(x: np.ndarray, k: int) -> np.ndarray:
        out = np.full(len(x), np.nan)
        if len(x) >= k:
            cs = np.concatenate(([0.0], np.cumsum(x)))
            out[k - 1:] = (cs[k:] - cs[:-k]) / k
        return out

    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    # حالة كل ساعة (مغلقة فقط: القيمة المتاحة عند نهاية الساعة i تُطبق من ساعة i+1)
    death = np.zeros(len(closes), dtype=bool)
    under = np.zeros(len(closes), dtype=bool)
    for i in range(len(closes)):
        if math.isfinite(sma50[i]) and math.isfinite(sma200[i]):
            death[i] = sma50[i] < sma200[i]
        if math.isfinite(sma200[i]) and i > 0:
            under[i] = closes[i] < sma200[i]
    hour_ms_close = (hour_keys + hr) if len(hour_keys) else np.zeros(0, dtype=np.int64)
    is_down = np.zeros(n, dtype=bool)
    if len(hour_ms_close):
        idx = np.searchsorted(hour_ms_close, t, side="right") - 1
        for i in range(n):
            j = idx[i]
            if j >= 0 and j < len(closes):
                # حالة الساعة المغلقة الأخيرة قبل هذه الشمعة (بلا نظرة مستقبلية)
                jj = j - 1 if (j >= 0 and idx[i] == j and hour_ms_close[j] > t[i]) else j
                if 0 <= jj < len(death):
                    is_down[i] = bool(death[jj] or under[jj])

    raw_cols, fin_cols, blk_cols = {}, {}, {}
    for k in kinds:
        raw_cols[k] = _col(res, f"{prefix}entry_raw_{k}", n)
        blk_cols[k] = _col(res, f"{prefix}entry_blocked_{k}", n)
        fin_cols[k] = _col(res, f"{prefix}entry_{k}", n)
    post_trend = {k: [1.0 if (fin_cols[k][i] >= 0.5 or blk_cols[k][i] >= 0.5) else 0.0
                      for i in range(n)] for k in kinds}

    def _surv(mask):
        raw = kept = 0
        for k in kinds:
            rc, fc = post_trend[k], fin_cols[k]
            for i in range(n):
                if mask[i] and rc[i] >= 0.5:
                    raw += 1
                    if fc[i] >= 0.5:
                        kept += 1
        return {"raw": raw, "kept": kept,
                "survival_pct": round(kept / raw * 100.0, 2) if raw else 0.0}

    down_bars = int(is_down.sum())
    return {
        "down_bars": down_bars, "up_bars": n - down_bars,
        "down": _surv(is_down), "up": _surv(~is_down),
    }


def _osc_json_payload(res: dict, win: dict, series_filter, max_pts: int) -> dict:
    """سلاسل النسخ مُنزّلة العينات للشارت + تقرير النسخ + البوابة."""
    n = win["bars"]
    t = win["t"]
    idx = _stride_idx(n, max_pts)
    prefix = None
    for key in (res.get("series") or {}):
        if str(key).startswith("zzfetm_"):
            prefix = "zzfetm_osc_"
            break
        if str(key).startswith("zzfbm_"):
            prefix = "zzfbm_osc_"
            break
    series_payload = {}
    if prefix:
        for key, vals in (res.get("series") or {}).items():
            k = str(key)
            if not k.startswith(prefix):
                continue
            rest = k[len(prefix):]
            if "_" not in rest:
                continue
            iid, field = rest.rsplit("_", 1)
            if series_filter and iid not in series_filter:
                continue
            series_payload.setdefault(iid, {})[field] = [
                {"i": i, "t": int(t[i]), "v": _round(vals[i] if i < len(vals) else None, 4)}
                for i in idx
            ]
    gate = _col(res, ("zzfetm_" if prefix == "zzfetm_osc_" else "zzfbm_") + "osc_gate", n)
    osc_meta = (res.get("osc") or {})
    return {
        "series": series_payload,
        "instances": osc_meta.get("instances") or [],
        "counts": osc_meta.get("counts") or {},
        "warnings": (osc_meta.get("warnings") or [])[:200],
        "gate_open": osc_meta.get("gate_open"),
        "gate": [{"i": i, "t": int(t[i]), "v": int(1.0 if gate[i] >= 0.5 else 0.0)} for i in idx],
        "conditions_tree": osc_meta.get("conditions"),
    }


# ---------------------------------------------------------------------------
# نقاط النهاية
# ---------------------------------------------------------------------------
def api_catalog():
    counts = {"macd": 0, "rsi": 0, "mom": 0}
    for x in OSC_DOC_INSTANCES:
        counts[x["kind"]] += 1
    return {
        "service": SERVICE_SPEC,
        "version": SERVICE_VERSION,
        "core_version": MTF_OSC_CORE_VERSION,
        "cases_version": OSC_CASE_LIBRARY_VERSION,
        "timeframes": [
            {"id": tf, "ms": int(TF_REGISTRY[tf]["ms"]), "anchor": TF_REGISTRY[tf]["anchor"]}
            for tf in TF_ORDER
        ],
        "kinds": [
            {"kind": k, "fields": list(v),
             "params": (["period", "ma_length", "bb_std"] if k == "rsi"
                        else ["fast", "slow", "signal"] if k == "macd"
                        else ["length"])}
            for k, v in OSC_KIND_FIELDS.items()
        ],
        "ops": [">", ">=", "<", "<=", "==", "!=", "cross_above", "cross_below"],
        "doc": {
            "source": OSC_DOC_SOURCE, "url": OSC_DOC_URL,
            "instances": OSC_DOC_INSTANCES, "counts": counts,
            "total": len(OSC_DOC_INSTANCES),
        },
        "cases": OSC_CASE_CATALOG,
        "engines": [
            {"id": "trendy_macdized", "title": "ترنديه ماكديه — الترندية + الدمج",
             "base": "الترندية (zzfet → zzfetm)", "kinds": ["s1", "s2", "s3"],
             "spec": ZLF_E2E_TRENDY_MACD_SPEC},
            {"id": "blazing_macdized", "title": "ملتهبه ماكديه — الملتهبة + الدمج",
             "base": "الملتهبة (zzfb → zzfbm)", "kinds": ["s1", "s2", "s3", "n5", "n6"],
             "spec": ZLF_E2E_BLAZING_MACD_SPEC},
        ],
        "max_window_days": MAX_WINDOW_DAYS,
        "symbol_default": "SOLUSDT",
    }


def api_compute(body: dict):
    st = _load_state()
    merged = copy.deepcopy(st)
    for k in ("engine", "trend"):
        if k in body:
            merged[k] = body[k]
    from_ms = _to_ms((body.get("window") or {}).get("from", (merged.get("window") or {}).get("from")))
    to_ms = _to_ms((body.get("window") or {}).get("to", (merged.get("window") or {}).get("to")))
    instances = body.get("osc_instances", merged.get("osc_instances"))
    conditions = body.get("osc_conditions", merged.get("osc_conditions"))
    if body.get("identity"):
        instances, conditions = [], None
    if body.get("macro"):
        # تفعيل وحدة ماكرو بنقرة (master_any_case / master_strict / early_watch / ...)
        for entry in OSC_CASE_CATALOG:
            if entry["id"] == body["macro"]:
                conditions = copy.deepcopy(entry["tree"])
                break
    win = _load_window(from_ms, to_ms)
    with _LOCK:
        res = _run_engine(merged, win, instances, conditions)
        prefix = _engine_series_prefix(merged.get("engine"))
        kinds = _KINDS[merged.get("engine")]
        n = win["bars"]
        t = win["t"]
        c = win["c"]
        entries = {}
        totals = {"raw": 0, "trend_blocked": 0, "osc_blocked": 0, "final": 0}
        final_events = []
        for k in kinds:
            raw = _col(res, f"{prefix}entry_raw_{k}", n)
            blk = _col(res, f"{prefix}entry_blocked_{k}", n)
            iblk = _col(res, f"{prefix}entry_iblocked_{k}", n)
            fin = _col(res, f"{prefix}entry_{k}", n)
            entries[k] = {
                "raw": int(sum(1 for x in raw if x >= 0.5)),
                "trend_blocked": int(sum(1 for x in blk if x >= 0.5)),
                "osc_blocked": int(sum(1 for x in iblk if x >= 0.5)),
                "final": int(sum(1 for x in fin if x >= 0.5)),
            }
            totals["raw"] += entries[k]["raw"]
            totals["trend_blocked"] += entries[k]["trend_blocked"]
            totals["osc_blocked"] += entries[k]["osc_blocked"]
            totals["final"] += entries[k]["final"]
            if len(final_events) < 500:
                for i in range(n):
                    if fin[i] >= 0.5:
                        final_events.append({"kind": k, "bar": i, "t": int(t[i]),
                                             "iso": _iso(t[i]), "close": _round(c[i], 6)})
                        if len(final_events) >= 500:
                            break
        final_events.sort(key=lambda e: e["bar"])
        case_hits = _case_hits_from_series(res, prefix, win)
        regime = _regime_stats(res, prefix, kinds, win)
        osc_payload = _osc_json_payload(res, win, body.get("series_filter"),
                                        int(body.get("max_points", MAX_POINTS_DEFAULT)))
        idx = _stride_idx(n, int(body.get("max_points", MAX_POINTS_DEFAULT)))
        price = [{"i": i, "t": int(t[i]),
                  "o": _round(win["o"][i], 6), "h": _round(win["h"][i], 6),
                  "l": _round(win["l"][i], 6), "c": _round(win["c"][i], 6)}
                 for i in idx]
        dir_col = _col(res, f"{prefix}dir", n)
        trend_ok = _col(res, f"{prefix}trend_ok", n)
        return {
            "ok": True,
            "engine": merged.get("engine"),
            "window": {"from": _iso(from_ms), "to": _iso(to_ms),
                       "from_ms": from_ms, "to_ms": to_ms, "bars": n},
            "elapsed_s": res.get("_elapsed_s"),
            "price": price,
            "entries": entries, "totals": totals,
            "final_events": final_events,
            "dir": [{"i": i, "t": int(t[i]), "v": int(dir_col[i])} for i in idx],
            "trend_ok": [{"i": i, "t": int(t[i]), "v": int(1.0 if trend_ok[i] >= 0.5 else 0.0)} for i in idx],
            "cases": case_hits,
            "regime": regime,
            "osc": osc_payload,
        }


def api_cases(body: dict):
    st = _load_state()
    merged = copy.deepcopy(st)
    from_ms = _to_ms((body.get("window") or {}).get("from", (merged.get("window") or {}).get("from")))
    to_ms = _to_ms((body.get("window") or {}).get("to", (merged.get("window") or {}).get("to")))
    instances = body.get("osc_instances", merged.get("osc_instances"))
    win = _load_window(from_ms, to_ms)
    with _LOCK:
        t0 = time.perf_counter()
        matrix = compute_oscillator_matrix(win["candles"], instances)
        n = win["bars"]
        t = win["t"]
        osc_np = {iid: {f: _np_of(vals, n) for f, vals in fields.items()}
                  for iid, fields in (matrix.get("series") or {}).items()}
        avail = {str(rep.get("id")): bool(rep.get("available", True))
                 for rep in (matrix.get("instances") or [])}
        o = np.asarray(win["o"], dtype=np.float64)
        h = np.asarray(win["h"], dtype=np.float64)
        l = np.asarray(win["l"], dtype=np.float64)
        c = np.asarray(win["c"], dtype=np.float64)
        out = []
        for case in OSC_CASE_LIBRARY:
            tree, _ = normalize_osc_conditions(case["tree"])
            g, _ = evaluate_osc_conditions(tree, osc_np, o, h, l, c, n, osc_available=avail)
            hits = int(g.sum())
            entry = {"id": case["id"], "family": case["family"], "kind": case["kind"],
                     "title": case["title"], "hits": hits,
                     "pct_of_bars": round(hits / n * 100.0, 3) if n else 0.0}
            if hits:
                w = np.nonzero(g)[0]
                entry["first"] = {"bar": int(w[0]), "iso": _iso(t[w[0]]), "t": int(t[w[0]])}
                entry["samples"] = [{"bar": int(b), "iso": _iso(t[b]), "t": int(t[b])} for b in w[:5]]
            out.append(entry)
        return {
            "ok": True,
            "window": {"from": _iso(from_ms), "to": _iso(to_ms), "bars": n},
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "instances_report": matrix.get("instances") or [],
            "warnings": (matrix.get("warnings") or [])[:200],
            "cases": out,
        }


def api_backtest(body: dict):
    import asyncio
    import pandas as pd
    from app.services.strategy.schemas import StrategyConfig
    from app.services.strategy.strategy_engine1 import StrategyEngine, DecisionAction
    from app.services.strategy.presets import TRENDY_MACDIZED, BLAZING_MACDIZED

    st = _load_state()
    engine_id = body.get("engine", st.get("engine", "trendy_macdized"))
    from_ms = _to_ms((body.get("window") or {}).get("from", (st.get("window") or {}).get("from")))
    to_ms = _to_ms((body.get("window") or {}).get("to", (st.get("window") or {}).get("to")))
    instances = body.get("osc_instances", st.get("osc_instances"))
    conditions = body.get("osc_conditions", st.get("osc_conditions"))
    mode = str(body.get("mode", "gated"))   # gated | identity
    if mode == "identity":
        instances, conditions = [], None
    win = _load_window(from_ms, to_ms)

    payload = copy.deepcopy(
        TRENDY_MACDIZED if engine_id == "trendy_macdized" else BLAZING_MACDIZED
    )
    for ind in payload["strategy_config"]["indicators"]:
        if ind.get("name") in ("zigzag_fib_e2e_trendy_macd", "zigzag_fib_e2e_blazing_macd"):
            ind["params"]["osc_instances"] = instances
            ind["params"]["osc_conditions"] = conditions
            tr = st.get("trend") or {}
            ind["params"]["trend_periods"] = tr.get("trend_periods", [7, 15, 25])
            ind["params"]["trend_confirm"] = tr.get("trend_confirm", "majority")

    df = pd.DataFrame({"time": win["t"], "open": win["o"], "high": win["h"],
                       "low": win["l"], "close": win["c"], "volume": win["v"]})
    df.index = pd.DatetimeIndex(pd.to_datetime(win["t"], unit="ms", utc=True), name="time")
    df = df.drop(columns=["time"])
    n = len(df)
    o = win["o"]
    c = win["c"]

    async def _run():
        cfg = StrategyConfig(**payload["strategy_config"])
        engine = StrategyEngine(cfg)
        t0 = time.perf_counter()
        full = await engine._prepare_indicators(df)
        engine.full_data = full
        prep_s = time.perf_counter() - t0
        prefix = "ind_zzfetm_" if engine_id == "trendy_macdized" else "ind_zzfbm_"
        osc_cols = [c2 for c2 in full.columns if c2.startswith(prefix)]
        trades = []
        state = None
        n_buy = n_exit = 0
        t1 = time.perf_counter()
        for i in range(n - 1):
            decision = await engine.run(full, current_index=i, in_position=(state is not None))
            act = decision.action
            if act == DecisionAction.BUY and state is None:
                state = {"entry_bar": i, "entry_price": float(o[i + 1]), "reason": decision.reason}
                n_buy += 1
            elif state is not None and (
                    (isinstance(decision.metadata, dict) and decision.metadata.get("trigger") == "exit_rule")
                    or act == DecisionAction.SELL):
                exit_price = float(o[i + 1])
                trades.append({
                    "entry_bar": state["entry_bar"], "exit_bar": i,
                    "entry": state["entry_price"], "exit": exit_price,
                    "pnl_pct": (exit_price - state["entry_price"]) / state["entry_price"] * 100.0,
                    "entry_reason": state["reason"], "exit_reason": decision.reason,
                })
                state = None
                n_exit += 1
        loop_s = time.perf_counter() - t1
        if state is not None:
            trades.append({
                "entry_bar": state["entry_bar"], "exit_bar": n - 1,
                "entry": state["entry_price"], "exit": float(c[-1]),
                "pnl_pct": (float(c[-1]) - state["entry_price"]) / state["entry_price"] * 100.0,
                "entry_reason": state["reason"], "exit_reason": "end-of-window",
            })
        return trades, n_buy, n_exit, osc_cols, prep_s, loop_s

    with _LOCK:
        trades, n_buy, n_exit, osc_cols, prep_s, loop_s = asyncio.run(_run())
    wins = sum(1 for tr in trades if tr["pnl_pct"] > 0)
    total_ret = sum(tr["pnl_pct"] for tr in trades)
    reasons: dict = {}
    for tr in trades:
        reasons[tr["entry_reason"]] = reasons.get(tr["entry_reason"], 0) + 1
    return {
        "ok": True,
        "engine": engine_id, "mode": mode,
        "window": {"from": _iso(from_ms), "to": _iso(to_ms), "bars": n},
        "osc_columns": len(osc_cols),
        "stats": {
            "buys": n_buy, "exits": n_exit, "trades": len(trades), "wins": wins,
            "win_rate_pct": round(wins / len(trades) * 100.0, 2) if trades else 0.0,
            "total_return_pct": round(total_ret, 4),
            "elapsed_s": round(prep_s + loop_s, 2), "prep_s": round(prep_s, 2), "loop_s": round(loop_s, 2),
        },
        "reasons_histogram": dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:12]),
        "trades_shown": min(len(trades), MAX_TRADES_RETURNED),
        "trades": [
            {"entry_bar": tr["entry_bar"], "exit_bar": tr["exit_bar"],
             "entry_t": int(win["t"][tr["entry_bar"]]), "exit_t": int(win["t"][tr["exit_bar"]]),
             "entry_iso": _iso(win["t"][tr["entry_bar"]]), "exit_iso": _iso(win["t"][tr["exit_bar"]]),
             "entry": _round(tr["entry"], 6), "exit": _round(tr["exit"], 6),
             "pnl_pct": _round(tr["pnl_pct"], 4),
             "entry_reason": tr["entry_reason"], "exit_reason": tr["exit_reason"]}
            for tr in trades[:MAX_TRADES_RETURNED]
        ],
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
_ROUTES_GET = {
    "/api/ping": lambda: {
        "ok": True, "service": SERVICE_SPEC, "version": SERVICE_VERSION,
        "core": MTF_OSC_CORE_VERSION, "cases": OSC_CASE_LIBRARY_VERSION,
        "data": DATA_PATH,
    },
    "/api/catalog": api_catalog,
    "/api/state": lambda: {"ok": True, "state": _load_state(),
                           "warnings": _validate_state(_load_state())},
    "/api/data/range": lambda: (lambda d: {
        "ok": True, "symbol": "SOLUSDT", "tf": "1m", "bars": len(d["t"]),
        "first": {"ms": d["first"], "iso": _iso(d["first"])},
        "last": {"ms": d["last"], "iso": _iso(d["last"])},
    })(_data()),
}

_ROUTES_POST = {
    "/api/state": None,      # معالجة خاصة
    "/api/reset": None,
    "/api/compute": api_compute,
    "/api/cases": api_cases,
    "/api/backtest": api_backtest,
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: dict):
        body = _j(payload)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            fn = _ROUTES_GET.get(path)
            if fn is None:
                return self._send(404, {"error": f"مسار غير معروف: {path}"})
            return self._send(200, fn())
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self):
        _t_entry = time.perf_counter()
        path = self.path.split("?")[0]
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = {}
            if length:
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                except Exception as exc:
                    return self._send(400, {"error": f"جسم JSON غير صالح: {exc}"})
            sys.stderr.write("[timing] %s body-read %.3fs\n" % (path, time.perf_counter() - _t_entry))
            if path == "/api/state":
                if not isinstance(body, dict) or "osc_instances" not in body:
                    return self._send(400, {"error": "جسم الحالة يجب أن يحوي osc_instances"})
                _save_state_raw(body)
                return self._send(200, {"ok": True, "saved": True,
                                        "warnings": _validate_state(body)})
            if path == "/api/reset":
                st = _default_state()
                _save_state_raw(st)
                return self._send(200, {"ok": True, "reset": True, "state": st,
                                        "warnings": _validate_state(st)})
            fn = _ROUTES_POST.get(path)
            if fn is None:
                return self._send(404, {"error": f"مسار غير معروف: {path}"})
            out = fn(body or {})
            _t_fn = time.perf_counter()
            payload = _j(out)
            sys.stderr.write("[timing] %s fn=%.3fs json=%.3fs size=%dKB\n"
                             % (path, _t_fn - _t_entry, time.perf_counter() - _t_fn, len(payload) // 1024))
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return None
        except ValueError as exc:
            return self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"PRO73 Control Service on :{PORT} (src={SRC})")
    print(f"data={DATA_PATH} | state={STATE_FILE} | max_window_days={MAX_WINDOW_DAYS}")
    server.serve_forever()


if __name__ == "__main__":
    main()
