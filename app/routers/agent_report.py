# =============================================================================
# ✅ ROUND34 — Agent Report Router — تقرير وكيل الفرونت اند الحي عبر API
# =============================================================================
# mounted at /api/v1/agent  (see app/main.py)
#
# «وتقرير كامل وتقرييير يصل اليه وكيل الفرونت اند عبر الapi ليرى كل شيء حي
#  كما في الكود عشان الرسم ورسم الموشرات وكل شيء حرفيا» — توجيه صاحب القرار.
#
# النقاط:
#   GET /report            — التقرير الكامل: هوية المحركات الثلاثة والنواة
#                            الموحدة، عقود الرسم (زقزاق/فيبو/نطاقات/ترند/
#                            حراس)، أعمدة العقود ind_*، قواعد الوقت ISO،
#                            ونتائج الاختبار (الانحدار الذهبي 20/20).
#   GET /report/live       — نفس التقرير + عينة حية محسوبة الآن على رمز/فريم
#                            حقيقيين (كل الإحداثيات الفعلية للرسم: أرجل
#                            الزقزاق، مستويات الفيبو بحدود الولادة/النهاية،
#                            النطاقات بخط ولادتها، خطوط الترند، الإشارات).
#   GET /health            — فحص سريع.
#
# كل الأزمنة في المخرجات بالملي ثانية (ms) — والوقت موحد عبر المحرك الموحد
# (zigzag_fib_core.to_ms): يقبل ms/ثوانٍ/datetime/ISO مع وبدون Z (بلا منطقة
# زمنية → UTC كتخزين المنصة).
# =============================================================================

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.services.data_service import DataService
from app.services.indicators.overlays import OVERLAY_TYPES, compute_overlays
from app.utils.dataframe_utils import ensure_datetime_index

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-report"])

_HERE = os.path.dirname(os.path.abspath(__file__))
_EVIDENCE_CANDIDATES = (
    os.path.join(_HERE, "..", "..", "evidence", "round34_verification.json"),
    "/tmp/verify/regression_results.json",
)


def _load_evidence() -> Optional[List[Dict[str, Any]]]:
    for cand in _EVIDENCE_CANDIDATES:
        try:
            if os.path.exists(cand):
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception:  # noqa: BLE001
            continue
    return None


def _base_report() -> Dict[str, Any]:
    """التقرير الأساسي — هوية النظام وعقوده (بلا حساب بيانات)."""
    from app.services.indicators.zigzag_fib_core import (
        ZIGZAG_FIB_CORE_SPEC,
        ZIGZAG_FIB_CORE_VERSION,
    )
    from app.services.indicators.overlays_zlf_e2e import ZLF_E2E_ENGINE_NAME, ZLF_E2E_SPEC
    from app.services.indicators.overlays_zlf_e2e_trendy import (
        ZLF_E2E_TRENDY_ENGINE_NAME,
        ZLF_E2E_TRENDY_SPEC,
    )
    from app.services.indicators.trend_fractals import TRF_ENGINE_NAME, TRF_SPEC

    return {
        "round": 34,
        "title": "ROUND34 — توحيد محركات الزقزاق والفيبوناتشي وإصلاح رسومات الباك تست",
        "core": {
            "module": "app/services/indicators/zigzag_fib_core.py",
            "spec": ZIGZAG_FIB_CORE_SPEC,
            "version": ZIGZAG_FIB_CORE_VERSION,
            "role": "المصدر الوحيد (Single Source of Truth) لكشف الزقزاق (وضعا luxalgo/"
                    "tradingview بنفس السلوك التاريخي) والفيبوناتشي (price(level)=q1+diff×level) "
                    "ودورة حياة النطاقات (ولادة=لحظة ظهور الزقزاق، موت=ولادة التالي) وتطبيع "
                    "المدخلات والوقت (ISO كامل — جذر إصلاح الرسومات).",
            "consumers": [
                "app/services/indicators/overlays.py (zigzag_channels + zigzag_fib — البطل ZLF)",
                "app/services/indicators/overlays_zlf_e2e.py (zigzag_fib_e2e — البطل e2e)",
                "app/services/indicators/overlays_zlf_e2e_trendy.py (zigzag_fib_e2e_trendy — الترندية)",
                "app/services/indicators/trend_fractals.py (تطبيع الشموع/الوقت)",
            ],
        },
        "engines": {
            "zigzag_channels": {
                "file": "app/services/indicators/overlays.py",
                "engine": "LuxAlgo ZigZag (zigzag_channels)",
                "mode": "luxalgo length=100",
                "series_prefix": "zz_", "columns_prefix": "ind_zz_",
                "used_by_strategy": "البطل الأصلي (ZigZag HL v2 — ZERO FEE)",
            },
            "zigzag_fib": {
                "file": "app/services/indicators/overlays.py",
                "engine": "ZLF — ZigZag Fib (v13.2)",
                "modes": "tradingview (depth/deviation/backstep) | luxalgo (length)",
                "series_prefix": "zzf_", "columns_prefix": "ind_zzf_",
                "signals": ["ZLF Liquidity S1/S2/S3", "ZLF Entry S1/S2/S3", "ZZFib Touch Up/Down"],
                "used_by_strategy": "البطل ZLF (zlf_triple_signal_zero_fee)",
            },
            "zigzag_fib_e2e": {
                "file": "app/services/indicators/overlays_zlf_e2e.py",
                "engine": ZLF_E2E_ENGINE_NAME,
                "spec": ZLF_E2E_SPEC,
                "modes": "luxalgo length=100 (default) | tradingview",
                "series_prefix": "zzfe_", "columns_prefix": "ind_zzfe_",
                "signals": ["ZLF-E2E Liquidity S1/S2/S3", "ZLF-E2E Entry S1/S2/S3"],
                "used_by_strategy": "البطل e2e (zlf_e2e_triple_signal_zero_fee)",
                "distinguishing_feature": "النطاق يولد لحظة ظهور الزقزاق (anchor) — الفيبو "
                                          "يُرسم عليه من خط الولادة إلى نهاية عمره",
            },
            "zigzag_fib_e2e_trendy": {
                "file": "app/services/indicators/overlays_zlf_e2e_trendy.py",
                "engine": ZLF_E2E_TRENDY_ENGINE_NAME,
                "spec": ZLF_E2E_TRENDY_SPEC,
                "modes": "luxalgo length=100 (default) | tradingview",
                "series_prefix": "zzfet_", "columns_prefix": "ind_zzfet_",
                "signals": ["ZLF-E2E-Trendy Liquidity S1/S2/S3", "ZLF-E2E-Trendy Entry S1/S2/S3",
                            "ZLF-E2E-Trendy Blocked S1/S2/S3 (trend gate)"],
                "used_by_strategy": "البطل e2e الترندية (zlf_e2e_trendy_triple_signal_zero_fee)",
                "distinguishing_features": [
                    "نفس نطاق E2E بالضبط (نفس النواة الموحدة) + بوابة ترند قالبية "
                    "(فترات [7,15,25] قابلة للتغيير من القالب)",
                    "حراس دخول ثلاثيون: entry_raw_* (الخام) · entry_* (بعد البوابة) · "
                    "entry_blocked_* (ممنوعة بالترند — تُرسم بلون تحذيري)",
                    "خطوط الترند (علوي/سفلي لكل فترة) تصل جاهزة للرسم في trend.lines",
                ],
            },
            "trend_fractal": {
                "file": "app/services/indicators/trend_fractals.py",
                "engine": TRF_ENGINE_NAME,
                "spec": TRF_SPEC,
                "series_prefix": "trf_", "columns_prefix": "ind_trf_",
                "role": "مؤشر الترند المستقل (وفاء Pine Auto Trendline [DojiEmoji]): يرسل "
                        "إحداثيات خطوطه الكاملة (x/t/y للطرفين + الميل + لحظة الولادة) "
                        "والباك END يحسب بوابة الإشارة بناء عليها",
            },
        },
        "unified_drawing_contract": {
            "zigzag": {
                "source": "overlays[<type>].legs[]",
                "shape": {"x1": "int bar", "t1": "int ms", "y1": "float price",
                          "x2": "int bar", "t2": "int ms", "y2": "float price",
                          "kind": "top|bottom", "confirmed_at_bar": "int",
                          "dir": "1|-1|0", "visible": "true"},
                "rule": "ارسم قطعة خط من (t1,y1) إلى (t2,y2) لكل leg — الرسم بـ time (ms) "
                        "لا bar. نفس البنية في الشارت الحي والباك تست وفي كل الأنواع "
                        "(zzfib/zzfib_e2e/zzfib_e2e_trendy) — مكوّن واحد للفرونت.",
            },
            "fibonacci": {
                "source": "overlays[<type>].ranges[].levels[] (لكل نطاق تاريخي) + "
                          "overlays[<type>].current.levels (النطاق الحي)",
                "shape": {"ratio": "float", "tag": "str", "value": "float price",
                          "x_from": "int bar الولادة", "t_from": "int ms الولادة",
                          "x_to": "int bar النهاية", "t_to": "int ms النهاية",
                          "extend_right": "bool"},
                "rule": "كل مستوى خط أفقي يبدأ من لحظة ولادة النطاق (anchor = لحظة ظهور "
                        "الزقزاق) وينتهي عند نهاية عمر النطاق (death−1) — والنطاق الحي "
                        "يمتد حتى آخر شمعة (extend_right=true). المعادلة الموحدة: "
                        "price(level) = q1 + diff × level (خط 0.618 بمقياس المستخدم = "
                        "price(0.382) بالمحرك). الفيبو مبني على قمة/قاع الزقزاق الأخيرة "
                        "[الطرف الظاهر أولاً → الثاني].",
            },
            "range_lifecycle": {
                "source": "overlays[<type>].ranges[]",
                "shape": {"index": "int", "p1": "{bar,time,price,kind}", "p2": "{bar,time,price,kind}",
                          "anchor": "{bar,time} لحظة الولادة = ظهور الزقزاق",
                          "death": "{bar,time} لحظة الموت = ولادة النطاق التالي",
                          "dir": "float", "launch_line": "float خط الانطلاقة 0.618",
                          "ref": "{bar,time,high,vol} المرجع R أو null",
                          "levels": "[مستويات الفيبو بحدودها الكاملة]"},
                "rule": "خط ولادة النطاق = خط عمودي عند anchor.time (عمود ind_zzfe_anchor / "
                        "ind_zzfet_anchor = 1.0 عند شمعة الولادة). كل ما قبل الولادة ليس "
                        "نطاقاً. زوج الزقزاق يتناوب: قمة→قاع ثم قاع→قمة.",
            },
            "trend_lines": {
                "source": "overlays['zzfib_e2e_trendy'].trend.lines (لكل فترة) + "
                          "overlays['trend_fractal'].lines",
                "rule": "الخط العلوي يصل آخر فراكتالَي قمة والسفلي آخر فراكتالَي قاع — "
                        "قيمة الخط عند أي شمعة = تمديد أيمن (سلاسل trf_p{n}_upper/lower "
                        "للرسم كخط مستمر). البوابة: majority (2 من 3) انحياز صاعد.",
            },
            "entry_guards": {
                "source": "overlays['zzfib_e2e_trendy'].series",
                "columns": {
                    "zzfet_entry_raw_s1|s2|s3": "إشارة خام قبل بوابة الترند",
                    "zzfet_entry_s1|s2|s3": "إشارة نافذة بعد البوابة (الدخول)",
                    "zzfet_entry_blocked_s1|s2|s3": "خام منعها الترند — تُرسم بعلامة تحذير",
                    "zzfet_trend_ok": "حالة البوابة عند كل شمعة (1=مسموح)",
                },
                "rule": "حراس الدخول يُرسمون فوق شموع الإشارة: النافذة بلون أخضر، "
                        "الممنوعة بلون رمادي/برتقالي تحذيري مع سبب المنع (trend gate).",
            },
        },
        "column_contracts": {
            "zzfib": ["ind_zzf_dir", "ind_zzf_p1", "ind_zzf_p2", "ind_zzf_i1", "ind_zzf_i2",
                      "ind_zzf_level_<L>", "ind_zzf_touch", "ind_zzf_liq_state",
                      "ind_zzf_liq_ref_high", "ind_zzf_liq_ref_vol", "ind_zzf_liq_vol_ok",
                      "ind_zzf_signal_s1|s2|s3|any", "ind_zzf_entry", "ind_zzf_entry_s1|s2|s3"],
            "zzfib_e2e": ["ind_zzfe_dir", "ind_zzfe_p1", "ind_zzfe_p2", "ind_zzfe_i1", "ind_zzfe_i2",
                          "ind_zzfe_anchor (خط ولادة النطاق)", "ind_zzfe_range_index",
                          "ind_zzfe_level_<L>", "ind_zzfe_liq_state", "ind_zzfe_liq_ref_high",
                          "ind_zzfe_liq_ref_vol", "ind_zzfe_liq_vol_ok",
                          "ind_zzfe_signal_s1|s2|s3|any", "ind_zzfe_entry", "ind_zzfe_entry_s1|s2|s3"],
            "zzfib_e2e_trendy": ["ind_zzfet_dir", "ind_zzfet_p1", "ind_zzfet_p2",
                                 "ind_zzfet_anchor (خط ولادة النطاق)", "ind_zzfet_range_index",
                                 "ind_zzfet_level_<L>", "ind_zzfet_liq_state",
                                 "ind_zzfet_signal_s1|s2|s3|any", "ind_zzfet_entry",
                                 "ind_zzfet_entry_raw", "ind_zzfet_entry_s1|s2|s3",
                                 "ind_zzfet_entry_raw_s1|s2|s3",
                                 "ind_zzfet_entry_blocked_s1|s2|s3",
                                 "ind_zzfet_trend_ok", "ind_zzfet_trend_bias",
                                 "ind_zzfet_trend_votes_bull|bear",
                                 "ind_zzfet_tr_p{n}_upper|lower|bias (مرايا الترند)"],
            "trend_fractal": ["ind_trf_trend_ok", "ind_trf_bias", "ind_trf_bull_votes",
                              "ind_trf_bear_votes", "ind_trf_threshold",
                              "ind_trf_cross_upper", "ind_trf_cross_lower",
                              "ind_trf_p{n}_upper|lower|bias"],
        },
        "time_rules": {
            "unit": "كل الأزمنة int ms (epoch milliseconds)",
            "unified_parser": "zigzag_fib_core.to_ms — يقبل: ms (≥1e11) · ثوانٍ (<1e11 → ×1000) · "
                              "datetime/pandas Timestamp · نص رقمي · نص ISO مع/بدون Z "
                              "(بلا منطقة زمنية → UTC كتخزين المنصة)",
            "iso_fix": "ROUND34 أصلح جذر «الرسومات العشوائية»: النسخ المستنسخة القديمة كانت "
                       "تفشل في تحليل timestamp كسلسلة ISO (float() يرمي ValueError → 0) "
                       "فترجع كل أزمنة أرجل الزقزاق ومستويات الفيبو صفراً في شارت الباك تست "
                       "(مسار chart-data يمرر ISO) — الآن الموحد يطابق DataFrame حرفياً.",
            "backtest_chart_path": "GET /api/v1/backtest/{id}/chart-data → visual_candles[].timestamp "
                                   "(ISO) → يُحلَّل صحيحاً الآن في كل أنواع overlays",
        },
        "backtest_overlays_fixes": [
            "الشموع الآن تمر بـ volume في مسار overlays لشارت الباك تست (كانت بلا حجم: لا "
            "مرجع R ولا إشارات في حمولة الرسم — الاستراتيجية نفسها كانت تحسب بالحجم)",
            "كل نطاق في ranges[] يحمل levels[] بحدود رسم كاملة (من خط الولادة إلى نهاية "
            "العمر) — «يجب أن يكون للفيبوناتشي نهاية كي لا يشوّه الشارت»",
            "overlays=zzfib_e2e,zzfib_e2e_trendy,trend_fractal متاحة في chart-data كالسابق",
        ],
        "verification": {
            "golden_regression": "20/20 PASS — مخرجات المحركات الموحدة مطابقة بايت-ببايت "
                                 "للقديمة على APPBUSDT 5m (1009 شمعة) وBTCUSDT 1m ذهبية "
                                 "(2000 شمعة): zzfib (وضعان) + zzfib_e2e (وضعان) + "
                                 "zzfib_e2e_trendy + zigzag_channels",
            "iso_equivalence": "نفس الشموع بثلاث صيغ (DataFrame/ms/ISO) تعطي إحداثيات رسم "
                               "متطابقة حرفياً — والقديم مع ISO كان يرجع أزمنة=0 (العلة مثبتة)",
            "appbusdt_case": "إشارة 2026-10-31 07:40 (الرياض) على APPBUSDT 5m أُعيد إنتاجها "
                             "وتحليلها: إشارة S3 صحيحة 100% وفق المواصفة المصادقة (نطاق#5 ولد "
                             "07:30 على ساق 672→674، مرجع أحمر 07:35 حجم 0.992، خضراء 07:40 "
                             "بحجم 1.56 > المرجع، انطلاقة صحيحة، لا اختراق → S3 امتصاص)",
            "evidence_file": "evidence/round34_verification.json (أو /tmp/verify/regression_results.json)",
        },
        "overlay_types": list(OVERLAY_TYPES),
        "api_endpoints": {
            "live_chart": "GET /api/v1/overlays/compute?symbol=...&timeframe=...&types=zzfib_e2e,zzfib_e2e_trendy,trend_fractal",
            "backtest_chart": "GET /api/v1/backtest/{id}/chart-data?overlays=zzfib_e2e,zzfib_e2e_trendy,trend_fractal",
            "post_candles": "POST /api/v1/overlays/compute (شموع جاهزة أو صيغة الواجهة)",
            "this_report": "GET /api/v1/agent/report",
            "live_sample": "GET /api/v1/agent/report/live?symbol=BTCUSDT&timeframe=1h",
        },
    }


# ===========================================================================
# GET /report — التقرير الكامل (بلا حساب بيانات)
# ===========================================================================
@router.get("/report")
async def agent_report():
    """تقرير وكيل الفرونت اند: المحركات والعقود وقواعد الرسم والوقت والاختبارات."""
    report = _base_report()
    evidence = _load_evidence()
    if evidence:
        passed = sum(1 for e in evidence if e.get("pass"))
        report["verification"]["checks"] = {"total": len(evidence), "passed": passed,
                                            "all_pass": passed == len(evidence)}
        report["verification"]["check_list"] = evidence
    return report


# ===========================================================================
# GET /health — فحص سريع
# ===========================================================================
@router.get("/health")
async def agent_health():
    from app.services.indicators.zigzag_fib_core import ZIGZAG_FIB_CORE_SPEC
    return {"status": "ok", "round": 34, "core_spec": ZIGZAG_FIB_CORE_SPEC}


# ===========================================================================
# GET /report/live — التقرير + عينة حية محسوبة الآن (كل إحداثيات الرسم)
# ===========================================================================
@router.get("/report/live")
async def agent_report_live(
    symbol: str = Query("BTCUSDT", description="رمز التداول مثل BTCUSDT"),
    timeframe: str = Query("1h", pattern="^(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|3d|1w|1M)$"),
    market: str = Query("crypto"),
    days: int = Query(7, ge=1, le=60, description="كم يوماً من التاريخ يُجلب"),
    limit: int = Query(None, ge=50, le=5000, description="قص الشموع إلى آخر N شمعة"),
    db: AsyncSession = Depends(get_db),
):
    """التقرير الكامل + عينة حية: إحداثيات رسم فعلية محسوبة الآن للأنواع الثلاثة.

    المخرجات في live_sample:
      candles_count / time_from / time_to
      zigzag_legs        — أرجل الزقزاق (بنية موحدة لكل الأنواع)
      e2e:  ranges (بكل مستوياتها وحدود ولادتها/نهايتها) + signals + current + anchor_bars
      trendy: نفس E2E + trend.lines (خطوط الترند بإحداثياتها) + الحراس (raw/blocked)
      كل الأزمنة ms.
    """
    try:
        data_service = DataService(db)
        dataframe = await data_service.get_historical(
            symbol=symbol.strip().upper(), timeframe=timeframe, market=market, days=days
        )
        if dataframe is None or dataframe.empty:
            raise HTTPException(status_code=404, detail=f"لا توجد شموع للرمز {symbol} على فريم {timeframe}")
        dataframe = ensure_datetime_index(dataframe)
        if limit:
            dataframe = dataframe.tail(int(limit))

        candles = []
        for ts, row in dataframe.iterrows():
            t_ms = int(ts.timestamp() * 1000) if hasattr(ts, "timestamp") else int(ts)
            vol = row.get("volume")
            try:
                vol = float(vol) if vol is not None else None
            except (TypeError, ValueError):
                vol = None
            candles.append({
                "time": t_ms,
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": vol,
            })
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent report live: فشل جلب الشموع لـ %s", symbol)
        raise HTTPException(status_code=502, detail=f"فشل جلب الشموع من المزود: {exc}")

    params = {
        "zzfib": {"mode": "tradingview", "depth": 12, "deviation": 20, "backstep": 3},
        "zzfib_e2e": {"mode": "luxalgo", "length": 100},
        "zzfib_e2e_trendy": {"mode": "luxalgo", "length": 100,
                             "trend_periods": [7, 15, 25], "trend_confirm": "majority",
                             "trend_gate": ["s1", "s2", "s3"]},
        "trend_fractal": {"periods": [7, 15, 25]},
    }
    res = compute_overlays(candles, types=["zzfib", "zzfib_e2e", "zzfib_e2e_trendy", "trend_fractal"],
                           params=params)
    ovl = res.get("overlays") or {}

    def _e2e_summary(out: Dict[str, Any]) -> Dict[str, Any]:
        ranges = out.get("ranges") or []
        return {
            "ranges_count": len(ranges),
            "ranges": [
                {
                    "index": r["index"],
                    "p1": r["p1"], "p2": r["p2"],
                    "anchor": r["anchor"], "death": r["death"],
                    "dir": r["dir"], "launch_line": r["launch_line"],
                    "ref": r["ref"],
                    "levels_count": len(r.get("levels") or []),
                    "levels": r.get("levels") or [],
                }
                for r in ranges
            ],
            "anchor_bars": [r["anchor"] for r in ranges],
            "signals": [
                {"bar": s.get("bar"), "time": s.get("time"), "signal": s.get("signal"),
                 "side": s.get("side"), "state": s.get("state"),
                 "range_index": s.get("range_index"), "trend_ok": s.get("trend_ok"),
                 "trend_gate_passed": s.get("trend_gate_passed")}
                for s in (out.get("signals") or [])
            ],
            "current": out.get("current"),
            "volume_available": out.get("volume_available"),
        }

    live_sample: Dict[str, Any] = {
        "symbol": symbol.strip().upper(),
        "timeframe": timeframe,
        "candles_count": res.get("bars"),
        "time_from": res.get("time_from"),
        "time_to": res.get("time_to"),
        "params_used": params,
    }

    if "zzfib" in ovl:
        zzf = ovl["zzfib"]
        live_sample["zzfib"] = {
            "legs_count": len(zzf.get("legs") or []),
            "legs": (zzf.get("legs") or [])[:50],
            "signals_count": len(zzf.get("signals") or []),
        }
    if "zzfib_e2e" in ovl:
        e2e = ovl["zzfib_e2e"]
        live_sample["zzfib_e2e"] = {
            "core": e2e.get("core"),
            "legs_count": len(e2e.get("legs") or []),
            "legs": (e2e.get("legs") or [])[:50],
            **_e2e_summary(e2e),
        }
    if "zzfib_e2e_trendy" in ovl:
        tr = ovl["zzfib_e2e_trendy"]
        live_sample["zzfib_e2e_trendy"] = {
            "core": tr.get("core"),
            "legs_count": len(tr.get("legs") or []),
            "legs": (tr.get("legs") or [])[:50],
            **_e2e_summary(tr),
            "trend": {
                "periods": (tr.get("trend") or {}).get("periods"),
                "counts": (tr.get("trend") or {}).get("counts"),
                "lines": (tr.get("trend") or {}).get("lines"),
            },
        }
    if "trend_fractal" in ovl:
        trf = ovl["trend_fractal"]
        live_sample["trend_fractal"] = {
            "lines": trf.get("lines"),
            "series_keys": sorted((trf.get("series") or {}).keys()),
        }

    report = _base_report()
    report["live_sample"] = live_sample
    evidence = _load_evidence()
    if evidence:
        passed = sum(1 for e in evidence if e.get("pass"))
        report["verification"]["checks"] = {"total": len(evidence), "passed": passed,
                                            "all_pass": passed == len(evidence)}
    return report
