# -*- coding: utf-8 -*-
"""
ROUND32 — الاختبار الحقيقي الشامل لاستراتيجية «الزقزاق البطل e2e الترنديه»
==========================================================================
الطور A — باك تست حقيقي (بيانات Binance SPOT الخام) على مصفوفة عملات × فريمات:
          كل خلية تُشغَّل مرتين: E2E الأصلية (بدون بوابة) ثم الترندية (بالبوابة)
          — للمقارنة المباشرة: صفقات، أرباح، نسبة الفلترة، الزمن.
الطور B — طبقة الشارت: أعمدة zzfet_* و trf_* على نفس البيانات + اتفاق
          بوابة الترند في محرك الاستراتيجية مع أغلبية خطوط trend_fractal المستقل.
الطور C — عدّ الإشارات الخام/المعتمدة/الممنوعة من الأعمدة (شفافية كاملة).
الطور D — الأداء: زمن الجلب والحساب والمحاكاة لكل خلية + إنتاجية شمعة/ثانية.
كل نتيجة تُحفظ فوراً في JSON (فشل خلية لا يضيع باقي الاختبار).
"""
import os
import sys
import json
import copy
import time
import traceback
from datetime import datetime, timezone, timedelta

PROJECT = "/home/z/my-project/user-project"
sys.path.insert(0, PROJECT)
os.chdir(PROJECT)

import pandas as pd  # noqa: E402

from app.backtest.engine1 import BacktestEngine  # noqa: E402
from app.backtest.schemas import BacktestConfig  # noqa: E402
from app.services.strategy.presets import (  # noqa: E402
    ZLF_E2E_TRIPLE_SIGNAL,
    ZLF_E2E_TRENDY_TRIPLE_SIGNAL,
)

sys.path.insert(0, "/home/z/my-project/download/ROUND23-REAL-TEST")
from zlf_fetch import fetch_klines, klines_to_df  # noqa: E402

OUT = "/home/z/my-project/download/ROUND32-E2E-TRENDY/evidence/realtest"
os.makedirs(OUT, exist_ok=True)

K3 = timezone(timedelta(hours=3))

# ---------------------------------------------------------------------------
# مصفوفة الاختبار: 6 عملات متنوعة × فريمين متنوعين لكل واحدة = 12 خلية
# الأيام مضبوطة لكل فريم (نفس روح عقد الجولة 23 — أيام متغيرة حسب الفريم)
# ---------------------------------------------------------------------------
MATRIX = [
    ("BTCUSDT", "1m", 2),
    ("BTCUSDT", "15m", 30),
    ("BTCUSDT", "1d", 600),
    ("ETHUSDT", "5m", 7),
    ("ETHUSDT", "1h", 120),
    ("SOLUSDT", "15m", 30),
    ("SOLUSDT", "4h", 400),
    ("BNBUSDT", "1m", 2),
    ("BNBUSDT", "1h", 120),
    ("XRPUSDT", "5m", 7),
    ("XRPUSDT", "1d", 600),
    ("RUNEUSDT", "1m", 2),
    ("RUNEUSDT", "4h", 400),
]

WINDOW_CANDLES = 2000          # عقد الإشارة الحية
CHAMPION_SL_PERCENT = 2.0      # SL القالب البطل
CHAMPION_TP_PERCENT = 99.0     # TP القالب البطل


class StubDataService:
    def __init__(self, df):
        self._df = df

    async def get_historicallastvirsion(self, **kw):
        return self._df.copy()


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import threading

        res = {}

        def _runner():
            try:
                res["ok"] = asyncio.run(coro)
            except Exception as e:  # noqa: BLE001
                res["err"] = e

        th = threading.Thread(target=_runner)
        th.start()
        th.join()
        if "err" in res:
            raise res["err"]
        return res["ok"]
    return asyncio.run(coro)


def run_bt(df, symbol, timeframe, start, end, strategy_config, sl=None, tp=None):
    cfg_kwargs = dict(
        name=f"round32-test:{symbol}:{timeframe}",
        symbols=[symbol],
        timeframe=timeframe,
        market="crypto",
        start_date=start,
        end_date=end,
        initial_capital=10000.0,
        position_size_percent=1.0,
        fill_model="next_open",
        tz_offset_minutes=0,
        strategy_config=copy.deepcopy(strategy_config),
    )
    if sl is not None:
        cfg_kwargs["stop_loss_percent"] = sl
    if tp is not None:
        cfg_kwargs["take_profit_percent"] = tp
    config = BacktestConfig(**cfg_kwargs)
    engine = BacktestEngine(StubDataService(df))
    return asyncio_run(engine.run_backtest(config))


def trades_digest(result):
    trs = []
    for t in (getattr(result, "trades", None) or []):
        et = getattr(t, "entry_time", None)
        xt = getattr(t, "exit_time", None)
        trs.append({
            "entry_time": int(pd.Timestamp(et).timestamp() * 1000) if et is not None else None,
            "exit_time": int(pd.Timestamp(xt).timestamp() * 1000) if xt is not None else None,
            "entry_price": getattr(t, "entry_price", None),
            "exit_price": getattr(t, "exit_price", None),
            "exit_reason": getattr(t, "exit_reason", None),
            "pnl": getattr(t, "pnl", None),
        })
    return trs


def entries_of(result):
    out = []
    for tp in (getattr(result, "trade_points", None) or []):
        if isinstance(tp, dict) and tp.get("type") == "entry":
            ts = tp.get("timestamp")
            ts = int(pd.Timestamp(ts).timestamp() * 1000) if ts is not None else None
            out.append({
                "time": ts,
                "price": tp.get("entry_price") or tp.get("price"),
                "reason": tp.get("decision_reason"),
            })
    out.sort(key=lambda x: x["time"] or 0)
    return out


def stats_of(trades):
    closed = [t for t in trades if t["pnl"] is not None and t["exit_reason"] != "End of Data"]
    wins = [t for t in closed if (t["pnl"] or 0) > 0]
    losses = [t for t in closed if (t["pnl"] or 0) <= 0]
    total_pnl = sum((t["pnl"] or 0) for t in closed)
    wr = round(100.0 * len(wins) / len(closed), 2) if closed else None
    return {
        "trades_total": len(trades),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": wr,
        "pnl_sum": round(total_pnl, 2),
    }


# ---------------------------------------------------------------------------
# حساب المؤشر على طبقة الشارت (نفس محرك الجولة 32) — لإحصاء الخام/المعتمد/الممنوع
# ---------------------------------------------------------------------------
def compute_trendy_columns(df):
    """يعيد DataFrame الأعمدة من محرك الترندية (نفس ما تحمله شموع الشارت)."""
    from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy

    candles = []
    for ts, r in df.iterrows():
        candles.append({
            "time": int(ts.timestamp() * 1000),
            "open": float(r["open"]), "high": float(r["high"]),
            "low": float(r["low"]), "close": float(r["close"]),
            "volume": float(r.get("volume", 0.0) or 0.0),
        })
    t0 = time.perf_counter()
    res = zigzag_fib_e2e_trendy(candles, mode="luxalgo", length=100,
                                trend_periods=[7, 15, 25], trend_confirm="majority",
                                trend_gate=["s1", "s2", "s3"])
    elapsed = time.perf_counter() - t0
    return res, elapsed


def signal_counts_from_columns(res):
    """عدّ الخام/المعتمد/الممنوع من سلاسل الإشارة (zzfet_entry_raw_s* إلخ)."""
    cols = res.get("series") or {}

    def _sum(*keys):
        tot = 0
        for k in keys:
            for v in (cols.get(k) or []):
                if v is not None and not (isinstance(v, float) and pd.isna(v)) and v > 0:
                    tot += 1
        return tot

    raw = _sum("zzfet_entry_raw_s1", "zzfet_entry_raw_s2", "zzfet_entry_raw_s3")
    adm = _sum("zzfet_entry_s1", "zzfet_entry_s2", "zzfet_entry_s3")
    blk = _sum("zzfet_entry_blocked_s1", "zzfet_entry_blocked_s2", "zzfet_entry_blocked_s3")
    return raw, adm, blk


RESULTS = {"meta": {
    "started_at": datetime.now(K3).isoformat(),
    "matrix": [f"{s}@{tf}({d}d)" for s, tf, d in MATRIX],
    "contract": {"window": WINDOW_CANDLES, "sl": CHAMPION_SL_PERCENT, "tp": CHAMPION_TP_PERCENT,
                 "fill_model": "next_open", "fee": 0.0},
}, "backtest": [], "chart_layer": []}


def save():
    with open(os.path.join(OUT, "realtest_results.json"), "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1, default=str)


# ===========================================================================
# الطوار A+B+C — لكل خلية: جلب → E2E → الترندية → أعمدة الشارت → عدّ الإشارات
# ===========================================================================
def main():
    for sym, tf, days in MATRIX:
        cell = {"symbol": sym, "timeframe": tf, "days": days}
        print(f"\n=== CELL {sym} {tf} ({days}d) ===", flush=True)
        try:
            # 1) جلب البيانات الحقيقية
            t0 = time.perf_counter()
            tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
                     "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}[tf]
            need = days * {"1m": 1440, "5m": 288, "15m": 96, "1h": 24, "4h": 6, "1d": 1}[tf]
            need = min(need, 45000)
            kl = fetch_klines(sym, tf, need)
            df, _forming = klines_to_df(kl, tf_ms, int(time.time() * 1000))
            df = df[~df.index.duplicated(keep="last")]
            fetch_s = round(time.perf_counter() - t0, 2)
            cell["fetch_seconds"] = fetch_s
            cell["candles"] = int(len(df))
            cell["range_utc"] = [str(df.index[0]), str(df.index[-1])]
            print(f"  fetched {len(df)} candles in {fetch_s}s", flush=True)

            start = df.index[0].to_pydatetime()
            end = df.index[-1].to_pydatetime()

            # 2) E2E الأصلية (بدون بوابة) — المرجع للمقارنة
            t0 = time.perf_counter()
            r_e2e = run_bt(df, sym, tf, start, end, ZLF_E2E_TRIPLE_SIGNAL["strategy_config"])
            e2e_s = round(time.perf_counter() - t0, 2)
            tr_e2e = trades_digest(r_e2e)
            en_e2e = entries_of(r_e2e)
            st_e2e = stats_of(tr_e2e)
            cell["e2e"] = {**st_e2e, "entries": len(en_e2e), "engine_seconds": e2e_s}
            print(f"  E2E   : entries={len(en_e2e)} trades={st_e2e['closed']} "
                  f"WR={st_e2e['win_rate_pct']} PnL={st_e2e['pnl_sum']} ({e2e_s}s)", flush=True)

            # 3) الترندية (البوابة مفعّلة 7/15/25 majority)
            t0 = time.perf_counter()
            r_tr = run_bt(df, sym, tf, start, end, ZLF_E2E_TRENDY_TRIPLE_SIGNAL["strategy_config"])
            tr_s = round(time.perf_counter() - t0, 2)
            tr_tr = trades_digest(r_tr)
            en_tr = entries_of(r_tr)
            st_tr = stats_of(tr_tr)
            cell["trendy"] = {**st_tr, "entries": len(en_tr), "engine_seconds": tr_s}
            print(f"  TRENDY: entries={len(en_tr)} trades={st_tr['closed']} "
                  f"WR={st_tr['win_rate_pct']} PnL={st_tr['pnl_sum']} ({tr_s}s)", flush=True)

            # 4) أعمدة الشارت + عدّ الخام/المعتمد/الممنوع + زمن الحساب
            res_ind, comp_s = compute_trendy_columns(df)
            cols = res_ind.get("series") or {}
            raw, adm, blk = signal_counts_from_columns(res_ind)
            trend_info = res_ind.get("trend") or {}
            cell["chart_layer"] = {
                "compute_seconds": round(comp_s, 3),
                "candles_per_sec": round(len(df) / comp_s, 1) if comp_s > 0 else None,
                "raw_signals": raw,
                "admitted_signals": adm,
                "blocked_signals": blk,
                "filter_pct": round(100.0 * blk / raw, 2) if raw else 0.0,
                "trend_periods": trend_info.get("periods"),
                "trend_threshold": trend_info.get("threshold"),
                "trend_lines_count": len(trend_info.get("lines") or []),
                "trend_ok_true_last": bool(
                    (cols.get("zzfet_trend_ok") or [None])[-1] not in (None, 0, False)),
            }
            cell["chart_layer"]["series_keys_present"] = sorted(cols.keys())
            print(f"  SIGNALS: raw={raw} admitted={adm} blocked={blk} "
                  f"({cell['chart_layer']['filter_pct']}% filtered) compute={comp_s:.3f}s "
                  f"({cell['chart_layer']['candles_per_sec']} c/s)", flush=True)

            # 5) اتساق البوابة: عدد إشارات الترندية المعتمدة ≤ الخام دائماً
            cell["consistency"] = {
                "raw_equals_e2e_entries": (raw == len(en_e2e)),
                "admitted_plus_blocked_equals_raw": (adm + blk == raw),
                "trendy_entries_le_admitted": (len(en_tr) <= adm),
            }
            print(f"  CONSISTENCY: {cell['consistency']}", flush=True)

            # عينات صفقات للتقرير (أول 5)
            cell["sample_trades_trendy"] = tr_tr[:5]
            cell["sample_trades_e2e"] = tr_e2e[:5]

        except Exception as e:  # noqa: BLE001
            cell["error"] = f"{type(e).__name__}: {str(e)[:400]}"
            traceback.print_exc()
        RESULTS["backtest"].append(cell)
        save()

    RESULTS["meta"]["finished_at"] = datetime.now(K3).isoformat()
    save()
    print("\nALL CELLS DONE →", OUT, flush=True)


if __name__ == "__main__":
    main()
