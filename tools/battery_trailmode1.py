#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TRAILMODE1 — البطارية المحلية (الفارق الدلالي + الهوية بت-بت).

الرقعة: TP3-SLTRAIL1 (post_tree) + TRAILMODE1 (حقل trailing_stop_mode).
  pre_tree  = شجرة TP3-SLTRAIL1 المنشورة (قبل TRAILMODE1).
  post_tree = بعد TRAILMODE1 (هذه الجولة).

الاختبارات:
U  (وحدة الصيغة — داخل العملية): دالة الخط `_trail_stop_level` حرفيًا:
   peak_pct (التاريخي): LONG: قمة×(1−frac) · SHORT: قمة×(1+frac)
   rise_pct (طلب المهندس محمد: «احسب من سعر الشراء الى اعلى قمه، اذا
   نزل 15% من اجمالي هذا الارتفاع فهذا يعتبر ستوب تريلينق»):
   LONG: قمة − frac×(القمة−الدخول) · SHORT: قاع + frac×(الدخول−القاع)
   · قمة=دخول (صفر ارتفاع) ⇒ الخط عند الدخول نفسه (حماية التعادل).
T1/T2/T4 (الهوية بت-بت — بلا نمط): نفس حمولات بطارية TP3 حرفيًا —
   كل السلوك التداولي pre= post (لا مفتاح يُبث ⇒ صفر فرق).
M1 (القدرة): T4 + trailing_stop_mode="rise_pct" ⇒ نتائج مختلفة عن T4 ·
   كل خروج «Trailing Stop» فوق قاع الستوب (entry×0.95) · صدى المخاطر
   يحمل trailing_stop_mode="rise_pct" + دلالة النمط.
M2 (الصيغة داخل المحاكاة — برهان قاطع): لكل خروج «Trailing Stop» في
   وضع rise: القمة يُعاد بناؤها من شموع المدة [entry_time, exit_time]
   (القمة في المحرك تبدأ من سعر الدخول وتتضمن أعلى شمعة حتى شمعة
   الخروج) ثم يُفحص: exit ≤ (1−frac)·قمة + frac·دخول (+ ε).
M3 (الافتراضي الصريح): T4 + trailing_stop_mode="peak_pct" (صريحًا) ≡
   T4 بلا النمط — بت-بت (الافتراضي الصريح = الافتراضي الضمني).

Usage: python3 tools/battery_trailmode1.py [u|t1|t2|t4|m1|m3|compare|all]
"""
import asyncio
import io
import json
import sys
import types
from pathlib import Path

BASE = Path("/home/z/my-project/trading-system/trailmode1")
PRE_TREE = BASE / "pre_tree"
POST_TREE = BASE / "post_tree"
DATA_15M = Path("/home/z/my-project/trading-system/split-zz/data/MMTUSDT_15m.json")
PAYLOAD_SRC = Path("/home/z/my-project/trading-system/split-zz/payloads/payload_qmom1_mmt_10000604.json")
OUT = BASE / "results"
OUT.mkdir(exist_ok=True)

SPLITS = [
    {"gain_percent": 4.7, "size_percent": 33.33},
    {"gain_percent": 7.4, "size_percent": 33.33},
]
TRAIL = 15.0
SL = 5.0
FRAC = TRAIL / 100.0

_ds_mod = types.ModuleType("app.services.data_service")


class _StubDataServiceCls:
    pass


_ds_mod.DataService = _StubDataServiceCls


def load_runtime(which: str):
    rt = PRE_TREE if which == "pre" else POST_TREE
    sys.path.insert(0, str(rt))
    sys.modules["app.services.data_service"] = _ds_mod
    import app.backtest.engine1 as e1
    return e1


def make_payload(variant: str):
    p = json.load(io.open(PAYLOAD_SRC, encoding="utf-8"))
    p.pop("structure_split_exits", None)
    p.pop("take_profit_splits", None)
    if variant == "T1":  # تريلينق + تصريف (بلا ستوب) — بلا نمط
        p["trailing_stop_percent"] = TRAIL
        p["take_profit_splits"] = json.loads(json.dumps(SPLITS))
    elif variant == "T2":  # ستوب + تصريف (بلا تريلينق)
        p["stop_loss_percent"] = SL
        p["take_profit_splits"] = json.loads(json.dumps(SPLITS))
    elif variant == "T4":  # الثلاثة معًا — بلا نمط (حمولة اليوم بت-بت)
        p["stop_loss_percent"] = SL
        p["trailing_stop_percent"] = TRAIL
        p["take_profit_splits"] = json.loads(json.dumps(SPLITS))
    elif variant == "M1":  # ✅ الجوهر: الثلاثة + rise_pct
        p["stop_loss_percent"] = SL
        p["trailing_stop_percent"] = TRAIL
        p["trailing_stop_mode"] = "rise_pct"
        p["take_profit_splits"] = json.loads(json.dumps(SPLITS))
    elif variant == "M3":  # الافتراضي الصريح = الافتراضي الضمني
        p["stop_loss_percent"] = SL
        p["trailing_stop_percent"] = TRAIL
        p["trailing_stop_mode"] = "peak_pct"
        p["take_profit_splits"] = json.loads(json.dumps(SPLITS))
    else:
        raise ValueError(variant)
    return p


def check(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    return bool(cond)


def _run_code(which: str, variant: str):
    """تشغيل متغير على شجرة في عملية مستقلة (نمط الجولات المقبولة)."""
    p = make_payload(variant)
    # الحمولة عبر ملف مؤقت (أضمن من التضمين داخل سلسلة الكود)
    payload_file = BASE / "payloads" / f"_battery_{variant}.json"
    with io.open(payload_file, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    rt = PRE_TREE if which == "pre" else POST_TREE
    code = (
        "import sys, json, asyncio, types, io\n"
        "mod = types.ModuleType('app.services.data_service')\n"
        "class _S: pass\n"
        "mod.DataService = _S\n"
        "sys.modules['app.services.data_service'] = mod\n"
        f"sys.path.insert(0, '{rt}')\n"
        "import app.backtest.engine1 as e1\n"
        "from app.backtest.schemas import BacktestConfig\n"
        "import pandas as pd\n"
        f"p = json.load(io.open('{payload_file}', encoding='utf-8'))\n"
        f"candles = json.load(io.open('{DATA_15M}', encoding='utf-8'))\n"
        "df = pd.DataFrame([{'open': float(c['open']), 'high': float(c['high']), 'low': float(c['low']), 'close': float(c['close']), 'volume': float(c['volume'])} for c in candles])\n"
        "df.index = pd.DatetimeIndex(pd.to_datetime([c['time'] for c in candles], unit='ms', utc=True), name='time')\n"
        "class StubDS:\n"
        "    def __init__(self, df): self.dfs = {'15m': df}\n"
        "    async def get_historicallastvirsion(self, symbol, timeframe, market, start_date, end_date, use_cache=True, tz_offset_minutes=0):\n"
        "        return self.dfs.get(str(timeframe), self.dfs['15m']).copy()\n"
        "cfg = BacktestConfig(**p)\n"
        "eng = e1.BacktestEngine(data_service=StubDS(df))\n"
        "res = asyncio.run(eng.run_backtest(cfg))\n"
        "trades = getattr(res, 'trades', None) or []\n"
        "tp = res.trade_points or []\n"
        "d = {\n"
        " 'total_pnl': float(res.total_pnl), 'total_pnl_percent': float(res.total_pnl_percent),\n"
        " 'final_capital': float(res.final_capital), 'total_trades': int(res.total_trades),\n"
        " 'win_rate': float(res.win_rate), 'equity_curve': [float(x) for x in res.equity_curve],\n"
        " 'trade_pnls': [float(t.pnl or 0.0) for t in trades],\n"
        " 'trade_entry_prices': [float(t.entry_price) for t in trades],\n"
        " 'trade_exit_prices': [float(t.exit_price or 0.0) for t in trades],\n"
        " 'trade_exit_reasons': [str(t.exit_reason) for t in trades],\n"
        " 'trade_entry_times': [str(t.entry_time) for t in trades],\n"
        " 'trade_exit_times': [str(t.exit_time) for t in trades],\n"
        " 'n_entry_points': sum(1 for q in tp if q.get('type') == 'entry'),\n"
        " 'n_exit_points': sum(1 for q in tp if q.get('type') == 'exit'),\n"
        " 'n_partial_points': sum(1 for q in tp if q.get('type') == 'partial_exit'),\n"
        " 'visual_candles_len': len(res.visual_candles or []),\n"
        " 'risk_echo': ((getattr(res, 'math_audit', None) or {}).get('risk_echo') or {}),\n"
        "}\n"
        f"json.dump(d, io.open(r'{OUT}/battery_{variant}_{which}.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)\n"
        f"print('[{variant}_{which}] pnl=%s trades=%s partials=%s' % (d['total_pnl'], d['total_trades'], d['n_partial_points']))\n")
    return code


def run_sub(which: str, variant: str):
    import subprocess
    code = _run_code(which, variant)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                        timeout=480, cwd=str(BASE))
    if r.returncode != 0:
        print(f"[{variant}_{which}] فشل التشغيل:\n{r.stderr[-1500:]}")
        return False
    print(r.stdout.strip()[-200:])
    return True


def unit_tests():
    """U — وحدة الصيغة (داخل العملية — post_tree مباشرة)."""
    print("[U · وحدة صيغة الخط]")
    e1 = load_runtime("post")
    L = e1._trail_stop_level
    f = 0.15
    ok = True
    # LONG: قمة 110 من دخول 100 (ارتفاع 10) — peak_pct: 93.5 · rise_pct: 108.5
    ok &= check(abs(L("peak_pct", 110.0, 100.0, f, "LONG") - 93.5) < 1e-12,
                "peak_pct LONG: 110×0.85 = 93.5 (النزول 15% من القمة السعرية)")
    ok &= check(abs(L("rise_pct", 110.0, 100.0, f, "LONG") - 108.5) < 1e-12,
                "rise_pct LONG: 110 − 0.15×(110−100) = 108.5 (النزول 15% من إجمالي الارتفاع)")
    # LONG: قمة 200 من دخول 100 (ارتفاع 100) — peak_pct: 170 · rise_pct: 185
    ok &= check(abs(L("peak_pct", 200.0, 100.0, f, "LONG") - 170.0) < 1e-12,
                "peak_pct LONG: 200×0.85 = 170")
    ok &= check(abs(L("rise_pct", 200.0, 100.0, f, "LONG") - 185.0) < 1e-12,
                "rise_pct LONG: 200 − 0.15×(200−100) = 185")
    # SHORT: قاع 80 من دخول 100 (ارتفاع 20 هبوطًا) — peak_pct: 92 · rise_pct: 83
    ok &= check(abs(L("peak_pct", 80.0, 100.0, f, "SHORT") - 92.0) < 1e-12,
                "peak_pct SHORT: 80×1.15 = 92")
    ok &= check(abs(L("rise_pct", 80.0, 100.0, f, "SHORT") - 83.0) < 1e-12,
                "rise_pct SHORT: 80 + 0.15×(100−80) = 83 (التنازل 15% من الربح)")
    # صفر ارتفاع ⇒ الخط عند الدخول (حماية التعادل)
    ok &= check(abs(L("rise_pct", 100.0, 100.0, f, "LONG") - 100.0) < 1e-12,
                "rise_pct بلا ارتفاع: الخط عند سعر الدخول (تعادل)")
    # بلا نمط ⇒ peak_pct بت-بت (نفس تعبير اليوم حرفيًا)
    ok &= check(L(None, 110.0, 100.0, f, "LONG") == 110.0 * (1.0 - f),
                "بلا نمط: LONG = قمة×(1−frac) بت-بت (نفس تعبير اليوم)")
    ok &= check(L(None, 80.0, 100.0, f, "SHORT") == 80.0 * (1.0 + f),
                "بلا نمط: SHORT = قمة×(1+frac) بت-بت")
    # العلاقة الجبرية: خط rise = خط peak + frac×الدخول (فرق ثابت)
    ok &= check(abs((L("rise_pct", 110.0, 100.0, f, "LONG")
                     - L("peak_pct", 110.0, 100.0, f, "LONG")) - f * 100.0) < 1e-12,
                "العلاقة الجبرية: rise − peak = frac×الدخول (15 نقطة عند دخول 100)")
    return ok


def m2_invariant(d):
    """M2 — برهان الصيغة داخل المحاكاة: إعادة بناء القمة من الشموع."""
    import pandas as pd
    candles = json.load(io.open(DATA_15M, encoding="utf-8"))
    highs = pd.Series([float(c["high"]) for c in candles],
                      index=pd.DatetimeIndex(
                          pd.to_datetime([c["time"] for c in candles], unit="ms", utc=True)))
    n_ok = 0
    n_bad = 0
    for entry, exitp, reason, et, xt in zip(
            d["trade_entry_prices"], d["trade_exit_prices"],
            d["trade_exit_reasons"], d["trade_entry_times"], d["trade_exit_times"]):
        if not reason.startswith("Trailing Stop"):
            continue
        et_i = pd.Timestamp(et)
        xt_i = pd.Timestamp(xt)
        peak = float(highs.loc[et_i:xt_i].max())
        line = (1.0 - FRAC) * peak + FRAC * entry
        if exitp <= line + 1e-9 * max(1.0, peak):
            n_ok += 1
        else:
            n_bad += 1
    return n_ok, n_bad


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    ok_all = True

    if mode in ("u", "all"):
        ok_all &= unit_tests()

    if mode in ("t1", "t2", "t4", "m1", "m3", "all"):
        todo = {
            "t1": [("pre", "T1"), ("post", "T1")],
            "t2": [("pre", "T2"), ("post", "T2")],
            "t4": [("pre", "T4"), ("post", "T4")],
            "m1": [("post", "M1")],
            "m3": [("post", "M3")],
        }[mode] if mode != "all" else [
            ("pre", "T1"), ("post", "T1"), ("pre", "T2"), ("post", "T2"),
            ("pre", "T4"), ("post", "T4"), ("post", "M1"), ("post", "M3"),
        ]
        for which, v in todo:
            ok_all &= run_sub(which, v)

    if mode in ("t1", "t2", "t4", "compare", "all"):
        # الهوية بت-بت: risk_echo مستبعد عمدًا (مفاتيح الشفافية الجديدة هي
        # التغيير التوثيقي المعلن؛ السلوك التداولي هو بوابة الهوية الصارمة)
        pairs = []
        if mode in ("t1", "all"):
            pairs.append(("T1", "تريلينق+تصريف (بلا نمط)"))
        if mode in ("t2", "all"):
            pairs.append(("T2", "ستوب+تصريف"))
        if mode in ("t4", "all"):
            pairs.append(("T4", "الثلاثة معًا (بلا نمط)"))
        for v, tag in pairs:
            pre = json.load(io.open(OUT / f"battery_{v}_pre.json", encoding="utf-8"))
            post = json.load(io.open(OUT / f"battery_{v}_post.json", encoding="utf-8"))
            pre.pop("risk_echo", None)
            post.pop("risk_echo", None)
            diffs = [k for k in pre if pre[k] != post[k]]
            ok_all &= not diffs
            print(f"[{v} · {tag}] هوية بت-بت:",
                  "PASS ✓" if not diffs else f"FAIL ✗ {diffs}")

    if mode in ("m3", "compare", "all"):
        # M3 — الافتراضي الصريح = الضمني بت-بت (السلوك التداولي فقط؛
        # الصدى يستبعد عمدًا لأنه يحمل النمط الصريح المعلَن — هذا هدفه)
        m3 = json.load(io.open(OUT / "battery_M3_post.json", encoding="utf-8"))
        t4 = json.load(io.open(OUT / "battery_T4_post.json", encoding="utf-8"))
        m3.pop("risk_echo", None)
        t4.pop("risk_echo", None)
        diffs = [k for k in t4 if t4[k] != m3.get(k)]
        m3b = json.load(io.open(OUT / "battery_M3_post.json", encoding="utf-8"))
        re_ok = (m3b.get("risk_echo") or {}).get("trailing_stop_mode") == "peak_pct"
        t4b = json.load(io.open(OUT / "battery_T4_post.json", encoding="utf-8"))
        t4_mode = (t4b.get("risk_echo") or {}).get("trailing_stop_mode")
        ok_all &= check(not diffs, f"M3: peak_pct الصريح ≡ بلا نمط بت-بت (فرق: {diffs})")
        ok_all &= check(t4_mode is None, f"T4 بلا نمط: الصدى trailing_stop_mode=None (وجدنا {t4_mode!r})")
        ok_all &= check(re_ok, "M3: الصدى يحمل trailing_stop_mode='peak_pct' الصريح")

    if mode in ("m1", "compare", "all"):
        m1 = json.load(io.open(OUT / "battery_M1_post.json", encoding="utf-8"))
        t4 = json.load(io.open(OUT / "battery_T4_post.json", encoding="utf-8"))
        print("[M1 · قدرة rise_pct]")
        diffs = [k for k in t4 if t4[k] != m1.get(k)]
        ok_all &= check(len(diffs) > 0, f"rise_pct يغيّر السلوك فعلاً عن peak_pct (الفروق: {len(diffs)} مفتاحًا)")
        re_ = m1.get("risk_echo") or {}
        ok_all &= check(re_.get("trailing_stop_mode") == "rise_pct",
                        "الصدى: trailing_stop_mode='rise_pct'")
        ok_all &= check(bool(re_.get("trailing_stop_semantics")),
                        "الصدى: دلالة النمط موجودة")
        ok_all &= check(re_.get("sl_trailing_coexist") is True
                        and re_.get("stop_loss_active") is True
                        and re_.get("trailing_active") is True,
                        "التعايش سليم داخل rise_pct (ستوب+تريلينق+جني مقسم)")
        # قاع الستوب: كل خروج تريلينق ≥ دخول×0.95 (الأولوية السببية)
        n_tr = 0
        n_floor_ok = 0
        for entry, exitp, reason in zip(m1["trade_entry_prices"],
                                        m1["trade_exit_prices"],
                                        m1["trade_exit_reasons"]):
            if not reason.startswith("Trailing Stop"):
                continue
            n_tr += 1
            if exitp >= entry * 0.95 - 1e-9:
                n_floor_ok += 1
        ok_all &= check(n_tr > 0, f"خروج تريلينق موجود في rise_pct (= {n_tr})")
        ok_all &= check(n_floor_ok == n_tr, f"كل خروج تريلينق فوق قاع الستوب {n_floor_ok}/{n_tr}")
        # M2 — برهان الصيغة (إعادة بناء القمة من الشموع)
        n_ok, n_bad = m2_invariant(m1)
        ok_all &= check(n_bad == 0,
                        f"M2: كل خروج تريلينق ≤ (1−15%)·قمة + 15%·دخول ({n_ok}/{n_ok + n_bad})")

    print()
    print("النتيجة الكلية:", "كل الاختبارات PASS ✓" if ok_all else "هناك فشل ✗")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
