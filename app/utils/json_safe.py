"""
JSON-safe response utilities.

Guarantees every HTTP JSON response is strictly RFC-compliant:
- numpy scalars (float64/int64/bool_) converted to native Python types
- NaN / ±Infinity converted to null (starlette serializes with allow_nan=False,
  so any leaking NaN would otherwise raise ValueError → HTTP 500)
- numpy arrays / pandas & datetime objects converted to JSON-friendly structures
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from typing import Any

import numpy as np
import pandas as pd
from starlette.responses import JSONResponse

__all__ = ["sanitize_json_value", "SafeJSONResponse"]

_MAX_DEPTH = 24

# ✅ R50 — مُسرّع orjson الاختياري: أسرع 3-5× من json القياسي في فك/تسلسل
# المستندات الضخمة (52-208MB) — أهميته هنا ليست السرعة فقط بل أن مدة
# احتجاز GIL (الذي يجمد حلقة الأحداث أثناء كود C) تتقلص بنفس النسبة.
# النتيجة متطابقة دلالياً (JSON مضغوط UTF-8 بلا أسكي-إسكاب).
try:
    import orjson as _orjson

    def _fast_dumps(obj) -> bytes:
        return _orjson.dumps(obj)
except Exception:  # noqa: BLE001 — orjson غير مثبت ⇒ json القياسي كما كان
    _orjson = None

    def _fast_dumps(obj) -> bytes:
        return json.dumps(
            obj, ensure_ascii=False, allow_nan=False,
            indent=None, separators=(",", ":"),
        ).encode("utf-8")


def _fast_loads(txt):
    """فك JSON سريع — orjson إن توفر وإلا json.loads القياسي."""
    if _orjson is not None:
        return _orjson.loads(txt)
    return json.loads(txt)


def sanitize_json_value(obj: Any, _depth: int = 0) -> Any:
    """Recursively convert numpy/pandas/NaN values into JSON-safe equivalents."""
    if _depth > _MAX_DEPTH:  # hard guard against pathological nesting
        return str(obj)

    if obj is None or isinstance(obj, (str, int, bool)):
        return obj

    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj

    if isinstance(obj, np.floating):  # np.float32/np.float64 (covers NaN/Inf too)
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f

    if isinstance(obj, np.integer):
        return int(obj)

    if isinstance(obj, np.bool_):
        return bool(obj)

    if isinstance(obj, np.ndarray):
        return sanitize_json_value(obj.tolist(), _depth + 1)

    if isinstance(obj, (pd.Timestamp, _dt.datetime, _dt.date, _dt.time)):
        return obj.isoformat()

    if isinstance(obj, dict):
        return {
            (k if isinstance(k, str) else str(k)): sanitize_json_value(v, _depth + 1)
            for k, v in obj.items()
        }

    if isinstance(obj, (list, tuple, set)):
        return [sanitize_json_value(v, _depth + 1) for v in obj]

    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):  # numpy scalar fallback
        try:
            return sanitize_json_value(obj.item(), _depth + 1)
        except Exception:
            return str(obj)

    if hasattr(obj, "isoformat"):
        return obj.isoformat()

    return obj


class SafeJSONResponse(JSONResponse):
    """JSONResponse that never fails on NaN/Infinity/numpy types."""

    def render(self, content: Any) -> bytes:
        # ✅ R50: orjson أولاً (متطابق دلالياً وأسرع 3-5×) — sanitize يعمل
        # قبل التسلسل في كلا المسارين فلا يمر NaN/Inf أبداً.
        if _orjson is not None:
            try:
                return _orjson.dumps(sanitize_json_value(content))
            except Exception:  # noqa: BLE001 — أنواع غير متوقعة ⇒ مسار آمن
                pass
        return json.dumps(
            sanitize_json_value(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")
