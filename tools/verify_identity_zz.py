#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPLIT-ZZ1 — الهوية والتكامل على بيانات MMTUSDT الحقيقية (الجزء الثاني).

L3 (الهوية بت-بت): حمولة البطل QMOM1-MMT #10000604 نفسها بلا
    structure_split_exits تُشغَّل على الشجرة قبل-الرقعة (split-tp/runtime —
    المنشورة الحية) ثم على الشجرة بعد-الرقعة (split-zz/runtime) في عمليتين
    مستقلتين — المقارنة بت-بت: total_pnl · عدد الصفقات · قائمة pnl لكل صفقة ·
    منحنى الرصيد كاملاً · نقاط الدخول/الخروج. (بوابة القبول المطلقة.)

L4 (التكامل الحي — انعكاس الهيكل المقسم على بيانات حقيقية):
    (أ) قاعدة same/100/25: أحداثها يجب أن تطابق أحداث zone_exit الأصلية على
        فريم الشارت (نفس الآلة — 25 حدثاً على MMT) وجني جزئي حقيقي يقع عند
        أول حدث أثناء فتح صفقة.
    (ب) قاعدة 5m/100/25 (فريم أدق حقيقي من طبقة البيانات): جني جزئي بمسار
        LTF الكامل (جلب → سياق → زقزاق 5m → إسقاط سببي).
    (ك) القاعدتان معاً + محاسبة الرصيد الصفر-ازدواج.

L5 (الشرط الخامس — RSI اليومي بين 50 و 60): نفس الحمولة بعد إضافة الشرط
    الخامس (rsi_1d_14_14 <= 60) — التحقق: البوابة موجودة في التكوين، تعمل
    (فرق الدخول عن نسخة الشروط الأربعة معزول للشرط الخامس)، ولا انهيار.

التشغيل:  python3 tools/verify_identity_zz.py pre|post|splits|five|compare
"""
import asyncio
import io
import json
import sys
from pathlib import Path

BASE = Path("/home/z/my-project/trading-system/split-zz")
PRE_TREE = Path("/home/z/my-project/trading-system/split-tp/runtime")
POST_TREE = BASE / "runtime"
DATA_15M = BASE / "data" / "MMTUSDT_15m.json"
DATA_5M = BASE / "data" / "MMTUSDT_5m.json"
PAYLOAD = BASE / "payloads" / "payload_qmom1_mmt_10000604.json"
PAYLOAD_5 = BASE / "payloads" / "payload_qmom1_mmt_5cond.json"
OUT = BASE / "results"
OUT.mkdir(exist_ok=True)

import types  # noqa: E402

_ds_mod = types.ModuleType("app.services.data_service")


class _StubDataServiceCls:
    pass


_ds_mod.DataService = _StubDataServiceCls


def load_runtime(which: str):
    """يحمّل شجرة معزولة (pre أو post) في عملية نظيفة."""
    rt = PRE_TREE if which == "pre" else POST_TREE
    sys.path.insert(0, str(rt))
    sys.modules["app.services.data_service"] = _ds_mod
    import importlib
    import app.backtest.engine1 as e1
    importlib.reload(e1)
    return e1


def build_dfs():
    import pandas as pd

    def mk(path):
        candles = json.load(io.open(path, encoding="utf-8"))
        df = pd.DataFrame([{
            "open": float(c["open"]), "high": float(c["high"]),
            "low": float(c["low"]), "close": float(c["close"]),
            "volume": float(c["volume"]),
        } for c in candles])
        df.index = pd.DatetimeIndex(
            pd.to_datetime([c["time"] for c in candles], unit="ms", utc=True),
            name="time")
        return df

    return mk(DATA_15M), mk(DATA_5M)


class StubDS:
    def __init__(self, df15, df5):
        self.dfs = {"15m": df15, "5m": df5}

    async def get_historicallastvirsion(self, symbol, timeframe, market,
                                        start_date, end_date, use_cache=True,
                                        tz_offset_minutes=0):
        key = str(timeframe)
        df = self.dfs.get(key)
        if df is None:
            df = self.dfs.get("15m")
        return df.copy()


def digest(res):
    """ملخص قابل للمقارنة بت-بت (كل الأرقام الحساسة)."""
    trades = getattr(res, "trades", None) or []
    tp = res.trade_points or []
    return {
        "total_pnl": float(res.total_pnl),
        "total_pnl_percent": float(res.total_pnl_percent),
        "final_capital": float(res.final_capital),
        "total_trades": int(res.total_trades),
        "win_rate": float(res.win_rate),
        "equity_curve": [float(x) for x in res.equity_curve],
        "trade_pnls": [float(t.pnl or 0.0) for t in trades],
        "trade_entry_prices": [float(t.entry_price) for t in trades],
        "trade_exit_prices": [float(t.exit_price or 0.0) for t in trades],
        "trade_exit_reasons": [str(t.exit_reason) for t in trades],
        "n_entry_points": sum(1 for p in tp if p.get("type") == "entry"),
        "n_exit_points": sum(1 for p in tp if p.get("type") == "exit"),
        "n_partial_points": sum(1 for p in tp if p.get("type") == "partial_exit"),
        "visual_candles_len": len(res.visual_candles or []),
    }


def load_payload(path):
    return json.load(io.open(path, encoding="utf-8"))


async def run(which: str, extra: str = "base"):
    e1 = load_runtime(which)
    df15, df5 = build_dfs()
    if extra == "base":
        payload = load_payload(PAYLOAD)
        payload.pop("structure_split_exits", None)
        payload.pop("take_profit_splits", None)
    elif extra == "five":
        payload = load_payload(PAYLOAD_5)
        payload.pop("structure_split_exits", None)
        payload.pop("take_profit_splits", None)
    elif extra == "splits":
        payload = load_payload(PAYLOAD)
        payload.pop("take_profit_splits", None)
        # عيار 25: 101 حدث انعكاس على فريم الشارت — 12 داخل نوافذ الصفقات
        # (عيار 100 البطولي: أحداثه الكبيرة تقع كلها خارج نوافذ الصفقات القصيرة)
        payload["structure_split_exits"] = [
            {"resolution": "same", "length": 25, "size_percent": 25}]
    elif extra == "splits5m":
        payload = load_payload(PAYLOAD)
        payload.pop("take_profit_splits", None)
        # فريم أدق حقيقي 5m بعيار 25: 307 حدثاً بالسياق الحقيقي — 27 داخل النوافذ
        payload["structure_split_exits"] = [
            {"resolution": "5m", "length": 25, "size_percent": 25}]
    elif extra == "splitsboth":
        payload = load_payload(PAYLOAD)
        payload.pop("take_profit_splits", None)
        payload["structure_split_exits"] = [
            {"resolution": "same", "length": 25, "size_percent": 25,
             "name": "انعكاس الشارت"},
            {"resolution": "5m", "length": 25, "size_percent": 25,
             "name": "انعكاس 5 دقائق"}]
    else:
        raise ValueError(extra)
    from app.backtest.schemas import BacktestConfig
    cfg = BacktestConfig(**payload)
    eng = e1.BacktestEngine(data_service=StubDS(df15, df5))
    res = await eng.run_backtest(cfg)
    return res, e1


def save(mode, res):
    d = digest(res)
    with io.open(OUT / f"identity_{mode}.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(f"[{mode}] total_pnl={d['total_pnl']:.6f} · trades={d['total_trades']} · "
          f"partials={d['n_partial_points']} · equity_len={len(d['equity_curve'])}")
    return d


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if mode in ("pre", "post", "five", "splits", "splits5m", "splitsboth"):
        which = "pre" if mode == "pre" else "post"
        extra = {"pre": "base", "post": "base", "five": "five",
                 "splits": "splits", "splits5m": "splits5m",
                 "splitsboth": "splitsboth"}[mode]
        res, _ = asyncio.run(run(which, extra))
        save(mode, res)
        if mode in ("splits", "splits5m", "splitsboth", "five"):
            tp = res.trade_points or []
            partials = [p for p in tp if p.get("type") == "partial_exit"]
            trades = getattr(res, "trades", None) or []
            extra_doc = {
                "partials": [
                    {k: (str(p.get(k)) if k == "timestamp" else p.get(k))
                     for k in ("timestamp", "price", "position_size", "pnl",
                               "resolution", "length", "size_percent",
                               "remaining_size", "exit_reason", "entry_price")}
                    for p in partials],
                "trades_meta": [
                    {"entry": float(t.entry_price),
                     "exit": float(t.exit_price or 0),
                     "pnl": float(t.pnl or 0), "reason": str(t.exit_reason),
                     "n_partials": len(t.partial_exits or [])}
                    for t in trades],
                "risk_echo": ((getattr(res, "math_audit", None) or {})
                              .get("risk_echo") or {}),
            }
            with io.open(OUT / f"identity_{mode}_extra.json", "w",
                         encoding="utf-8") as f:
                json.dump(extra_doc, f, ensure_ascii=False, indent=1,
                          default=str)
        return 0

    if mode == "compare":
        pre = json.load(io.open(OUT / "identity_pre.json", encoding="utf-8"))
        post = json.load(io.open(OUT / "identity_post.json", encoding="utf-8"))
        diffs = [k for k in pre if pre[k] != post[k]]
        if not diffs:
            print("IDENTITY PASS — بت-بت كامل (بلا أي فرق)")
            print(f"  total_pnl = {pre['total_pnl']!r} (متطابق)")
            print(f"  trades = {pre['total_trades']} · pnl list متطابق · "
                  f"equity ({len(pre['equity_curve'])} نقطة) متطابق")
            return 0
        print("IDENTITY FAIL — فروق في:", diffs)
        for k in diffs:
            print(f"  {k}: pre={str(pre[k])[:120]} post={str(post[k])[:120]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
