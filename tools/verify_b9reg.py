#!/usr/bin/env python3
# =============================================================================
# ✅ B9REG-FIX — بطارية التحقق الرسمية (7 فحوص) — تسجيل «ماكد 9B» في الأنابيب
# =============================================================================
# المشكلة التي يصلحها هذا الملف: دمج المشروع المدموج أسقط سطور تسجيل B9 من
# overlays.py و overlay_columns.py (الملفان اللذان عدّلتهما حزمة B9 أصلاً)
# فأصبح المؤشر b9_macd_gates "معروفاً" بالاسم لكن محوّل المعاملات يرجع None
# ⇒ columns_for_configs يتخطاه بصمت ⇒ لا عمود ind_b9g_buy ⇒ شرط الدخول
# indicator:b9_macd_gates:b9g_buy لا يُحل أبداً ⇒ 0 صفقات مع SUCCESS.
#
# التشغيل (بنفس مترجم celery — python3.11 دائماً):
#   /usr/local/bin/python3.11 tools/verify_b9reg.py            # من جذر الباك اند
#   /usr/local/bin/python3.11 tools/verify_b9reg.py /root/TR_platform/backend
# =============================================================================
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

RESULTS: list = []


def check(idx: int, name: str, fn) -> None:
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"استثناء: {e!r}"
    RESULTS.append((idx, name, bool(ok), str(detail)))
    mark = "✅" if ok else "❌"
    print(f"[{idx}/7] {name} {mark} — {detail}")


def _synthetic_candles(n: int = 600):
    """شموع اصطناعية حتمية (بلا شبكة) — كافية لإطلاق أعمدة b9g_* وجودها."""
    import pandas as pd

    t0 = 1735689600000  # 2025-01-01 UTC
    rows = []
    price = 2600.0
    for i in range(n):
        # مسار هابط ثم صاعد قوي — لضمان تنويع اتجاهات MACD
        drift = -0.4 if i < n * 0.4 else 1.1
        o = price
        c = o + drift
        h = max(o, c) + 0.8
        l = min(o, c) - 0.8
        rows.append(
            {
                "timestamp": pd.Timestamp(t0 + i * 900_000, unit="ms", tz="UTC"),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1000.0 + (i % 13),
            }
        )
        price = c
    return pd.DataFrame(rows)


def main() -> int:
    app_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    if not (app_root / "app" / "services").is_dir():
        print(f"❌ جذر تطبيق غير صالح: {app_root}")
        return 2
    sys.path.insert(0, str(app_root))

    # [1/7] استيراد الملفين المصلحين
    def _c1():
        oc = importlib.import_module("app.services.indicators.overlay_columns")
        ov = importlib.import_module("app.services.indicators.overlays")
        return True, f"overlays={getattr(ov, '__file__', '?').split('/')[-1]}, overlay_columns OK"

    check(1, "استيراد الملفين المصلحين", _c1)

    oc = importlib.import_module("app.services.indicators.overlay_columns")

    # [2/7] المرادفات الثلاثة + القاعدة في KNOWN_OVERLAY_BASES
    def _c2():
        for alias in ("b9_macd_gates", "b9", "b9_macd"):
            base = oc.normalize_overlay_name(alias)
            if base != "b9_macd_gates":
                return False, f"المرادف {alias} → {base!r} (المطلوب b9_macd_gates)"
        if "b9_macd_gates" not in oc.KNOWN_OVERLAY_BASES:
            return False, "b9_macd_gates ليس في KNOWN_OVERLAY_BASES"
        return True, "b9 / b9_macd / b9_macd_gates → b9_macd_gates + KNOWN_OVERLAY_BASES"

    check(2, "المرادفات وقاعدة b9 في السجل", _c2)

    # [3/7] محوّل المعاملات (كان يرجع None — سبب الصفر صفقات)
    def _c3():
        cfg = {
            "name": "b9_macd_gates",
            "params": {
                "instances": [
                    {"id": "macd_1d_6_13_4", "timeframe": "1D", "fast": 6, "slow": 13, "signal": 4}
                ],
                "active_start": "2025-01-05",
                "active_end": "2025-01-20",
            },
        }
        conv = oc.config_to_overlay_params(cfg)
        if not conv or "b9_macd_gates" not in conv:
            return False, f"config_to_overlay_params رجع {conv!r} — التسجيل ما زال مفقوداً"
        keys = set(conv["b9_macd_gates"].keys())
        need = {"instances", "active_start", "active_end"}
        if not need.issubset(keys):
            return False, f"معاملات ناقصة: {sorted(need - keys)}"
        return True, f"المعاملات تمر: {sorted(keys)}"

    check(3, "محوّل المعاملات b9 (كان None)", _c3)

    # [4/7] الأنابيب الكاملة: columns_for_configs تنتج أعمدة ind_b9g_*
    def _c4():
        df = _synthetic_candles()
        cfgs = [
            {"name": "b9_macd_gates", "params": {}},
            {"name": "trend_fractal", "params": {"periods": [100]}},
        ]
        cols = oc.columns_for_configs(df, cfgs)
        b9cols = sorted(k for k in cols if k.startswith("ind_b9g"))
        if "ind_b9g_buy" not in b9cols:
            return False, f"عمود ind_b9g_buy مفقود! الأعمدة: {b9cols[:5]}..."
        need = {"ind_b9g_buy", "ind_b9g_cond", "ind_b9g_sub_w_pos", "ind_b9g_sub_d_pos",
                "ind_b9g_sub_4h_core", "ind_b9g_sub_any_above_4h"}
        missing = need - set(b9cols)
        if missing:
            return False, f"أعمدة شفافية مفقودة: {sorted(missing)}"
        return True, f"{len(b9cols)} عمود ind_b9g_* (منها ind_b9g_buy والفروع الأربعة)"

    check(4, "الأنابيب الكاملة تنتج أعمدة b9g", _c4)

    # [5/7] المسار القديم (ترند-فركتال) لم يتأثر بت-بت
    def _c5():
        df = _synthetic_candles(400)
        cols = oc.columns_for_configs(df, [{"name": "trend_fractal", "params": {"periods": [100]}}])
        trf = sorted(k for k in cols if k.startswith("ind_trf"))
        need = {"ind_trf_p100_upper", "ind_trf_p100_lower", "ind_trf_p100_bias",
                "ind_trf_p100_new_upper", "ind_trf_bias", "ind_trf_trend_ok"}
        missing = need - set(trf)
        if missing:
            return False, f"أعمدة ترند-فركتال مفقودة: {sorted(missing)}"
        return True, f"{len(trf)} عمود ind_trf_* سليمة"

    check(5, "ترند-فركتال (خروج B9-T100) سليم", _c5)

    # [6/7] استيراد سلاسل الكمومية (سلامة الملفات الأخرى بعد النشر)
    def _c6():
        mods = [
            "app.services.indicators.overlays_zlf_e2e_trendy_quantum",
            "app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema",
            "app.services.indicators.overlays_b9_macd_gates",
        ]
        for m in mods:
            importlib.import_module(m)
        return True, "استيراد الكمومية + الكمومية-EMA + محرك B9 — كلها سليمة"

    check(6, "سلامة استيراد السلاسل الأخرى", _c6)

    # [7/7] compute_overlays بالنوع الصريح b9_macd_gates
    def _c7():
        ov = importlib.import_module("app.services.indicators.overlays")
        df = _synthetic_candles(400)
        res = ov.compute_overlays(df, types=["b9_macd_gates"], params={"b9_macd_gates": {}})
        b9 = (res or {}).get("overlays", {}).get("b9_macd_gates")
        if not isinstance(b9, dict) or not b9.get("series"):
            return False, f"compute_overlays لم يعد نتيجة b9_macd_gates: {type(b9)}"
        keys = sorted(k for k in b9["series"] if k.startswith("b9g_"))
        if "b9g_buy" not in keys:
            return False, f"b9g_buy مفقود من السلاسل: {keys[:6]}"
        return True, f"compute_overlays(b9_macd_gates) → {len(keys)} سلسلة b9g_*"

    check(7, "compute_overlays بمحرك B9 مباشرة", _c7)

    ok_all = all(r[2] for r in RESULTS)
    print()
    if ok_all:
        print("✅✅✅ ALL 7 CHECKS PASSED — تسجيل B9 مستعاد والأنابيب سليمة")
        return 0
    print("❌ فحوص فاشلة — راجع الأعلى")
    return 1


if __name__ == "__main__":
    sys.exit(main())
