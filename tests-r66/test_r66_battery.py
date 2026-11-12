# -*- coding: utf-8 -*-
"""
بطارية اختبار الجولة 66 — الحجم التراكمي (Compounding) في محرك الخروج.
"""

import importlib.util
import json
import random
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# يعمل في تخطيطين: <جذر>/tests-r66 مع <جذر>/src/app (بيئة التطوير)
# أو <جذر>/tests-r66 مع <جذر>/app مباشرة (جذر مشروع المستخدم).
_CANDIDATES = [os.path.join(HERE, "..", "src"), os.path.join(HERE, "..")]
SRC = next((p for p in _CANDIDATES
            if os.path.isfile(os.path.join(p, "app", "services", "exit_engine.py"))),
           _CANDIDATES[0])
sys.path.insert(0, os.path.abspath(SRC))

os.environ.setdefault("SECRET_KEY", "battery-only-secret-key-0123456789abcdef")
os.environ.setdefault("DEBUG", "true")

from app.services import exit_engine as NEW  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "exit_engine_r64_baseline", os.path.join(HERE, "exit_engine_r64_baseline.py")
)
OLD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OLD)

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} :: {detail}")
        print(f"  ✗ {name}  → {detail}")


def gen_candles(path_points, start_ts=1735689600000, step_ms=3600000):
    n = max(p[0] for p in path_points) + 2
    vals = [0.0] * n
    for k in range(len(path_points) - 1):
        i0, v0 = path_points[k]
        i1, v1 = path_points[k + 1]
        span = max(1, i1 - i0)
        for j in range(i0, i1 + 1):
            vals[j] = v0 + (v1 - v0) * (j - i0) / span
    vals[0] = path_points[0][1]
    out = []
    for i, c in enumerate(vals):
        o = vals[i - 1] if i else vals[0]
        hi = max(o, c) * 1.002
        lo = min(o, c) * 0.998
        out.append({"time": start_ts + i * step_ms,
                    "open": round(o, 4), "high": round(hi, 4),
                    "low": round(lo, 4), "close": round(c, 4)})
    return out


def sig(bar, price, floor):
    return {"bar": bar, "time": None, "price": price, "floor": floor,
            "floor_meta": {"source": "range"}, "signal": {"signal": "S1_Entry", "side": "buy"}}


print("=" * 78)
print("بطارية الجولة 66 — الحجم التراكمي في محرك استراتيجية الخروج")
print("=" * 78)

print("\n[A] التوافق الرجعي بت-بت (بلا أي حقل جديد ⇒ نفس نتائج R64 حرفياً)")

rng = random.Random(66666)
scenarios = []
for s in range(60):
    n = rng.randint(40, 160)
    pts = [(0, 100.0)]
    p = 100.0
    for k in range(1, rng.randint(3, 9)):
        p = max(20.0, p * (1 + rng.uniform(-0.12, 0.12)))
        pts.append((min(n - 2, int(k * n / 9)), round(p, 4)))
    pts.append((n - 1, pts[-1][1]))  # امتداد المسار ليغطي كامل النافذة n
    candles = gen_candles(pts)
    candles = candles[:n] if len(candles) > n else candles + [dict(candles[-1], time=candles[-1]["time"] + 3600000 * (k + 1)) for k in range(n - len(candles))]
    nsig = rng.randint(1, 6)
    signals = []
    for _ in range(nsig):
        b = rng.randint(1, n - 3)
        px = candles[b]["close"]
        signals.append(sig(b, px, round(px * rng.uniform(0.80, 0.97), 4)))
    cfg = {}
    if s % 2 == 0:
        cfg["position_size_usd"] = float(rng.choice([50, 100, 250]))
    if s % 3 == 0:
        cfg["take_profit_pct"] = rng.choice([1.5, 3.0, 6.0])
    if s % 4 == 1:
        cfg["dca1_trigger_pct"] = rng.choice([0.0, 2.0, 4.0])
        cfg["dca2_trigger_pct"] = rng.choice([0.0, 5.0, 8.0])
    if s % 5 == 2:
        cfg["fees_pct"] = rng.choice([0.0, 0.1])
    if s % 6 == 3:
        cfg["use_trailing"] = True
        cfg["trailing_giveback_pct"] = rng.choice([10.0, 25.0])
    if s % 7 == 4:
        cfg["fibo_floor_exit"] = False
        cfg["stop_loss_pct"] = rng.choice([0.0, 3.0])
    if s % 8 == 5:
        cfg["allow_overlap"] = True
    if s % 9 == 6:
        cfg["entry_exec"] = "next_open"
    if s % 10 == 7:
        cfg["cooldown_bars"] = rng.randint(0, 5)
    scenarios.append((candles, signals, cfg))

mismatch = 0
total_trades_a = 0
for i, (candles, signals, cfg) in enumerate(scenarios):
    r_old = OLD.run_exit_backtest(candles, signals, dict(cfg))
    r_new = NEW.run_exit_backtest(candles, signals, dict(cfg))
    total_trades_a += len(r_new.get("trades") or [])
    same_trades = json.dumps(r_old.get("trades"), sort_keys=True) == json.dumps(r_new.get("trades"), sort_keys=True)
    same_summary = json.dumps(r_old.get("summary"), sort_keys=True) == json.dumps(r_new.get("summary"), sort_keys=True)
    same_notes = json.dumps(r_old.get("notes"), sort_keys=True) == json.dumps(r_new.get("notes"), sort_keys=True)
    if not (same_trades and same_summary and same_notes):
        mismatch += 1
        if mismatch == 1:
            print("    أول عدم تطابق في سيناريو", i)
check("60 سيناريو حتمي × (trades+summary+notes) بت-بت", mismatch == 0, f"عدم تطابق: {mismatch}")
check("السيناريوهات أنتجت صفقات فعلاً (العينة حية)", total_trades_a > 30, f"صفقات: {total_trades_a}")

r_old = OLD.run_exit_backtest([], [], None)
r_new = NEW.run_exit_backtest([], [], None)
check("لا شموع + لا إشارات — نفس السلوك",
      r_old["notes"] == r_new["notes"] and r_new["summary"]["trades_total"] == 0)

print("\n[B] زوج A/B — البرهان المرئي للتراكم (entry_usd_by_trade)")

pts = [
    (0, 100.0), (8, 108.0),
    (14, 95.0), (22, 80.0),
    (30, 84.0), (36, 90.0),
    (44, 70.0), (52, 60.0),
    (60, 64.0), (66, 70.0),
    (74, 74.0), (82, 78.0),
]
candles = gen_candles(pts)
entries = [
    sig(2, candles[2]["close"], 92.0),
    sig(16, candles[16]["close"], 78.0),
    sig(31, candles[31]["close"], 80.0),
    sig(45, candles[45]["close"], 66.0),
    sig(61, candles[61]["close"], 61.0),
    sig(75, candles[75]["close"], 70.0),
]
common = {"take_profit_pct": 5.0, "dca1_trigger_pct": 0.0, "dca2_trigger_pct": 0.0,
          "max_entries": 1, "position_size_usd": 100.0}

rA = NEW.run_exit_backtest(candles, entries, dict(common))
rB = NEW.run_exit_backtest(candles, entries,
                           {**common, "position_sizing": "percent_of_equity",
                            "position_size_pct": 1.0},
                           initial_capital=10000.0)

check("A: نفس عدد الصفقات بين الوضعين", len(rA["trades"]) == len(rB["trades"]),
      f"A={len(rA['trades'])} B={len(rB['trades'])}")
sizes_A = {e["usd"] for t in rA["trades"] for e in t["entries"]}
check("A: مجموعة الأحجام وحيدة القيمة (100$)", sizes_A == {100.0}, f"{sizes_A}")
sizes_B = [t["entries"][0]["usd"] for t in rB["trades"]]
check("B: أول دورة = 1٪ × 10000 = 100$ بالضبط", bool(sizes_B) and abs(sizes_B[0] - 100.0) < 0.01,
      f"{sizes_B[:3]}")
check("B: الأحجام تتغير دورة بعد دورة (≠ قيمة وحيدة)", len(set(sizes_B)) > 1, f"{sizes_B}")
E = 10000.0
expected_sizes = []
for t in sorted(rB["trades"], key=lambda x: x["trade_id"]):
    expected_sizes.append(round(max(1.0, round(E * 0.01, 2)), 2))
    E += t["pnl_usd"]
check("B: كل حجم = round(E_before × 1٪, 2) بت-بت",
      all(abs(a - b) <= 0.01 for a, b in zip(sizes_B, expected_sizes)),
      f"فعلي {sizes_B} مقابل متوقع {expected_sizes}")

capB = rB["summary"]["capital"]
check("B: final_equity_usd == initial + Σ محقق",
      abs(capB["final_equity_usd"] - (10000.0 + sum(t["pnl_usd"] for t in rB["trades"] if not t["was_open_at_end"]))) <= 0.01,
      f"final={capB['final_equity_usd']}")
check("B: equity_growth_pct = (final/initial−1)×100",
      abs(capB["equity_growth_pct"] - (capB["final_equity_usd"] / 10000.0 - 1) * 100.0) <= 0.01)
audit = rB.get("compounding_audit")
check("B: compounding_audit موجود ومتسق",
      audit is not None and audit["consistent"] is True and audit["max_abs_error"] <= 0.011,
      json.dumps(audit, ensure_ascii=False)[:120] if audit else "غائب")
check("B: equity_curve[].equity_usd = initial + cumulative",
      all(abs(p["equity_usd"] - (10000.0 + p["cumulative_pnl_usd"])) <= 0.01
          for p in rB["summary"]["equity_curve"]))
check("B: كل صفقة تحمل equity_before/after_usd",
      all(("equity_before_usd" in t and "equity_after_usd" in t) for t in rB["trades"]))
check("B: بعد الإغلاق equity_after = before + pnl (المحقق)",
      all(abs(t["equity_after_usd"] - (t["equity_before_usd"] + t["pnl_usd"])) <= 0.01
          for t in rB["trades"] if not t["was_open_at_end"]))
check("A: الوضع الثابت بلا أي مفتاح R66 في summary/trades",
      all(k not in rA["summary"]["capital"] for k in ("position_sizing", "final_equity_usd"))
      and "equity_before_usd" not in rA["trades"][0]
      and "compounding_audit" not in rA
      and all("equity_usd" not in p for p in rA["summary"]["equity_curve"]))

print("\n[C] قواعد الحواف")

pts_small = [(0, 100.0), (6, 106.0), (12, 99.0), (20, 104.0)]
c_small = gen_candles(pts_small)
e_small = [sig(2, c_small[2]["close"], 90.0), sig(13, c_small[13]["close"], 90.0)]
r_dust = NEW.run_exit_backtest(c_small, e_small,
                               {"position_sizing": "percent_of_equity",
                                "position_size_pct": 0.5, "take_profit_pct": 4.0,
                                "max_entries": 1},
                               initial_capital=80.0)
check("C1: حجم تحت 1$ يُثبَّت على 1$ (دورتان)",
      bool(r_dust["trades"]) and all(t["entries"][0]["usd"] == 1.0 for t in r_dust["trades"]),
      f"{[t['entries'][0]['usd'] for t in r_dust['trades']]}")
check("C1: عدّاد dust_floored_entries يرصد التثبيت",
      r_dust["summary"]["capital"].get("dust_floored_entries", 0) >= 1,
      f"{r_dust['summary']['capital'].get('dust_floored_entries')}")

pts_wall = None
# سيناريو يدوي محكم: انهيار كامل لسعر 0 → E = 0 بالضبط → جدار التصفية
t0w = 1735689600000
c_wall = [
    {"time": t0w,       "open": 100.0, "high": 101.0,   "low": 99.0,  "close": 100.0},
    {"time": t0w + 1,   "open": 100.0, "high": 100.5,   "low": 99.5,  "close": 100.0},
    {"time": t0w + 2,   "open": 100.0, "high": 100.5,   "low": 0.0,   "close": 0.0},
    {"time": t0w + 3,   "open": 60.0,  "high": 62.0,    "low": 58.0,  "close": 60.0},
    {"time": t0w + 4,   "open": 61.0,  "high": 64.0,    "low": 59.0,  "close": 63.0},
]
e_wall = [sig(1, 100.0, 50.0), sig(3, 60.0, 40.0), sig(4, 63.0, 45.0)]
r_wall = NEW.run_exit_backtest(c_wall, e_wall,
                               {"position_sizing": "percent_of_equity",
                                "position_size_pct": 100.0, "take_profit_pct": 8.0,
                                "fees_pct": 0.0, "max_entries": 1},
                               initial_capital=100.0)
cap_w = r_wall["summary"]["capital"]
sigc = r_wall["summary"]["entry_signals"]
check("C2: account_liquidated=true عند استنفاد الرصيد",
      cap_w.get("account_liquidated") is True)
check("C2: final_equity_usd == 0 بالضبط (خسارة 100٪)",
      abs(cap_w["final_equity_usd"]) < 1e-9, f"{cap_w['final_equity_usd']}")
check("C2: صفقة واحدة فقط (لا دورات جديدة بعد التصفية)",
      len(r_wall["trades"]) == 1, f"{len(r_wall['trades'])}")
check("C2: عدّاد signals_ignored_liquidated == 2 (الإشارتان اللاحقتان)",
      sigc.get("signals_ignored_liquidated", 0) == 2, f"{sigc}")
check("C2: التدقيق متسق حتى مع التصفية",
      r_wall["compounding_audit"]["consistent"] is True)

pts_f = [(0, 100.0), (6, 106.0), (14, 99.0), (20, 105.0)]
c_f = gen_candles(pts_f)
e_f = [sig(2, c_f[2]["close"], 90.0), sig(15, c_f[15]["close"], 90.0)]
r_fee = NEW.run_exit_backtest(c_f, e_f,
                              {"position_sizing": "percent_of_equity",
                               "position_size_pct": 10.0, "fees_pct": 0.5,
                               "take_profit_pct": 4.0, "max_entries": 1},
                              initial_capital=1000.0)
t1, t2 = r_fee["trades"]
check("C3: الدورة الثانية تُقاس على الرصيد بعد خصم العمولات",
      abs(t2["entries"][0]["usd"] - round((1000.0 + t1["pnl_usd"]) * 0.10, 2)) <= 0.01,
      f"t2.usd={t2['entries'][0]['usd']}")

# سيناريو يدوي محكم: صفقة رابحة تُغلق بالهدف + صفقة تبقى مفتوحة عند النهاية
t0o = 1735693200000
c_o = [
    {"time": t0o,       "open": 100.0, "high": 101.0,  "low": 99.0,   "close": 100.0},
    {"time": t0o + 1,   "open": 100.0, "high": 100.5,  "low": 99.5,   "close": 100.0},
    {"time": t0o + 2,   "open": 100.5, "high": 102.0,  "low": 100.0,  "close": 101.5},
    {"time": t0o + 3,   "open": 101.5, "high": 103.5,  "low": 101.0,  "close": 103.0},
    {"time": t0o + 4,   "open": 103.0, "high": 104.5,  "low": 102.5,  "close": 104.2},
    {"time": t0o + 5,   "open": 104.0, "high": 104.3,  "low": 103.0,  "close": 103.5},
    {"time": t0o + 6,   "open": 103.5, "high": 103.8,  "low": 102.2,  "close": 103.0},
    {"time": t0o + 7,   "open": 103.0, "high": 103.2,  "low": 102.0,  "close": 102.6},
    {"time": t0o + 8,   "open": 102.6, "high": 102.8,  "low": 101.5,  "close": 102.2},
]
e_o = [sig(1, 100.0, 90.0), sig(6, 103.0, 50.0)]
r_open = NEW.run_exit_backtest(c_o, e_o,
                               {"position_sizing": "percent_of_equity",
                                "position_size_pct": 10.0, "take_profit_pct": 4.0,
                                "max_entries": 1},
                               initial_capital=1000.0)
open_trades = [t for t in r_open["trades"] if t["was_open_at_end"]]
closed_trades = [t for t in r_open["trades"] if not t["was_open_at_end"]]
check("C4: صفقة رابحة مغلقة + صفقة مفتوحة عند النهاية",
      len(closed_trades) == 1 and len(open_trades) == 1,
      f"مغلق={len(closed_trades)} مفتوح={len(open_trades)}")
if open_trades:
    ot = open_trades[0]
    check("C4: صفقة نهاية البيانات: equity_after == equity_before (لا تراكم)",
          ot["equity_after_usd"] == ot["equity_before_usd"])
check("C4: final_equity يعكس المحقق فقط (لا يشمل غير المحقق)",
      abs(r_open["summary"]["capital"]["final_equity_usd"]
          - (1000.0 + sum(t["pnl_usd"] for t in closed_trades))) <= 0.01)
check("C4: غير المحقق موجود في pnl.unrealized لكن خارج الرصيد",
      abs(r_open["summary"]["pnl"]["unrealized_usd_open_at_end"] - open_trades[0]["pnl_usd"]) <= 0.01
      if open_trades else False)

# سيناريو يدوي محكم: إشارتان قبل أي إغلاق (نفس الحجم) ثم ثالثة بعد تراكم الربحين
t0v = 1735696800000
c_ov = [
    {"time": t0v,       "open": 100.0, "high": 100.5,  "low": 99.5,   "close": 100.0},
    {"time": t0v + 1,   "open": 100.0, "high": 100.5,  "low": 99.5,   "close": 100.0},
    {"time": t0v + 2,   "open": 100.0, "high": 100.5,  "low": 99.5,   "close": 100.0},
    {"time": t0v + 3,   "open": 100.0, "high": 100.0,  "low": 99.0,   "close": 99.5},
    {"time": t0v + 4,   "open": 99.5,  "high": 100.0,  "low": 99.0,   "close": 99.5},
    {"time": t0v + 5,   "open": 99.5,  "high": 105.8,  "low": 99.4,   "close": 105.6},
    {"time": t0v + 6,   "open": 105.6, "high": 105.7,  "low": 104.5,  "close": 105.0},
    {"time": t0v + 7,   "open": 105.0, "high": 105.5,  "low": 104.5,  "close": 105.2},
    {"time": t0v + 8,   "open": 105.2, "high": 105.6,  "low": 104.8,  "close": 105.4},
]
e_ov = [sig(1, 100.0, 80.0), sig(2, 100.0, 80.0), sig(6, 105.0, 90.0)]
r_ov = NEW.run_exit_backtest(c_ov, e_ov,
                             {"position_sizing": "percent_of_equity",
                              "position_size_pct": 5.0, "take_profit_pct": 5.0,
                              "allow_overlap": True, "max_entries": 1},
                             initial_capital=2000.0)
ov = r_ov["trades"]
check("C5: ثلاث صفقات (متزامنتان + لاحقة)", len(ov) == 3, f"{len(ov)}")
if len(ov) == 3:
    a_usd, b_usd, c_usd = ov[0]["entries"][0]["usd"], ov[1]["entries"][0]["usd"], ov[2]["entries"][0]["usd"]
    check("C5: المتزامنتان بنفس الحجم بالضبط (E مجمّد أثناء الدورتين)",
          a_usd == 100.0 and b_usd == 100.0, f"A={a_usd} B={b_usd}")
    pnl_ab = ov[0]["pnl_usd"] + ov[1]["pnl_usd"]
    check("C5: الدورة اللاحقة تُقاس على E بعد تراكم الربحين",
          abs(c_usd - round((2000.0 + pnl_ab) * 0.05, 2)) <= 0.01,
          f"C={c_usd} متوقع={round((2000.0 + pnl_ab) * 0.05, 2)}")
    check("C5: كلتا المتزامنتين أُغلقتا معاً بالهدف عند نفس البار",
          ov[0]["exit"]["bar"] == ov[1]["exit"]["bar"] == 5
          and ov[0]["exit"]["reason"] == "take_profit", f"{ov[0]['exit']} | {ov[1]['exit']}")
check("C5: التدقيق متسق مع التزامن", r_ov["compounding_audit"]["consistent"] is True)

pts_dca = [(0, 100.0), (10, 92.0), (14, 90.0), (22, 99.0), (30, 105.0)]
c_dca = gen_candles(pts_dca)
e_dca = [sig(2, c_dca[2]["close"], 70.0)]
r_dca = NEW.run_exit_backtest(c_dca, e_dca,
                              {"position_sizing": "percent_of_equity",
                               "position_size_pct": 10.0, "take_profit_pct": 4.0,
                               "dca1_trigger_pct": 3.0, "dca2_trigger_pct": 6.0,
                               "max_entries": 3},
                              initial_capital=1000.0)
t_dca = r_dca["trades"][0]
usd_list = [e["usd"] for e in t_dca["entries"]]
check("C6: الدخول الأول = 10٪ × 1000 = 100$", abs(usd_list[0] - 100.0) <= 0.01, f"{usd_list}")
check("C6: التعزيزان بنفس قيمة الدخول الأول حرفياً (1:1:1)",
      len(set(usd_list)) == 1 and len(usd_list) >= 2, f"{usd_list}")
check("C6: cycle_usd مرفق بالصفقة", t_dca.get("cycle_usd") == usd_list[0])

print("\n[D] الفاليديشن العربي + المخطط + الوصف الديناميكي")

_, errs = NEW.normalize_exit_config({"position_sizing": "bogus"})
check("D: قيمة enum خاطئة → خطأ بالاسم", any("position_sizing" in e for e in errs))
_, errs = NEW.normalize_exit_config({"position_sizing": "percent_of_equity"})
check("D: تراكمي بلا نسبة → خطأ عربي صريح", any("يتطلب position_size_pct" in e for e in errs))
_, errs = NEW.normalize_exit_config({"position_sizing": "percent_of_equity", "position_size_pct": 0.05})
check("D: نسبة تحت 0.1 → خارج النطاق", any("خارج النطاق [0.1..100]" in e for e in errs))
_, errs = NEW.normalize_exit_config({"position_sizing": "percent_of_equity", "position_size_pct": 101})
check("D: نسبة فوق 100 → خارج النطاق", any("خارج النطاق [0.1..100]" in e for e in errs))
_, errs = NEW.normalize_exit_config({"initial_capital": 0})
check("D: بذرة ≤ 0 → خطأ عربي", any("initial_capital" in e for e in errs))
cfg_x, errs_x = NEW.normalize_exit_config({"position_size_pct": 55})
check("D: نسبة وحدها في الوضع الثابت مسموحة", errs_x == [])
cfg_y, errs_y = NEW.normalize_exit_config({})
check("D: الحمولة الفارغة = افتراضات بت-بت (fixed_usd)",
      errs_y == [] and cfg_y["position_sizing"] == "fixed_usd"
      and cfg_y["position_size_pct"] is None and cfg_y["initial_capital"] is None)

sch = NEW.EXIT_CONFIG_SCHEMA
check("D: الحقول الثلاثة في المخطط مع label_ar/desc_ar",
      all(k in sch and "label_ar" in sch[k] and "desc_ar" in sch[k]
          for k in ("position_sizing", "position_size_pct", "initial_capital")))
check("D: مخطط النسبة بنفس نطاق المحرك الرئيسي [0.1..100]",
      sch["position_size_pct"]["min"] == 0.1 and sch["position_size_pct"]["max"] == 100.0)

desc_fix = NEW.describe_exit_config(cfg_y)
cfg_cmp, _ = NEW.normalize_exit_config({"position_sizing": "percent_of_equity", "position_size_pct": 2.5})
desc_cmp = NEW.describe_exit_config(cfg_cmp)
check("D: الوصف الثابت يذكر المبلغ الثابت", "بقيمة 100$" in desc_fix)
check("D: الوصف التراكمي يذكر النسبة والرصيد الجاري",
      "من الرصيد الجاري" in desc_cmp and "2.5٪" in desc_cmp)
check("D: الوصف التراكمي يحتوي النص التعاقدي الحرفي",
      "الوضع التراكمي: كل دخول (الأول + التعزيزان) = النسبة × الرصيد الجاري" in desc_cmp)
check("D: الوصف يوثّق جدار التصفية والأرضية",
      "جدار التصفية" in desc_cmp and "تُثبّت على 1$" in desc_cmp)

print("\n[E] المسار الموحد run_unified_exit_backtest (بذرة الجذر + صدى config_effective)")

from app.routers import exit_strategy as _es  # noqa: E402
from app.services import unified_backtest as UB  # noqa: E402


def fake_zzfib(*args, **params):
    p1 = [None] * len(candles)
    p2 = [None] * len(candles)
    d = [None] * len(candles)
    signals = []
    for k in (2, 16, 31, 45, 61, 75):
        if k < len(candles):
            px = args[1][k]["close"]
            p1[k] = round(px * 1.06, 4)
            p2[k] = round(px * 0.88, 4)
            d[k] = -1.0
            signals.append({"bar": k, "time": args[1][k]["time"], "price": px,
                            "signal": "S1_Entry", "side": "buy"})
    return {"series": {"zzf_p1": p1, "zzf_p2": p2, "zzf_dir": d},
            "signals": signals, "ranges": [], "pivots": []}


_orig_run_strategy = _es._run_strategy
_es._run_strategy = fake_zzfib
try:
    candles_u = gen_candles(pts)
    meta_u = {"symbol": "BTCUSDT", "timeframe": "1h", "market": "crypto",
              "initial_capital": 10000.0, "timezone": "UTC",
              "tz_offset_minutes": 0, "name": "battery-r66"}

    old_cfg, errs_old = UB.validate_exit_block("zzfib", None, {"take_profit_pct": 5.0})
    check("E: validate_exit_block يقبل الحمولة القديمة", errs_old == [])

    ru_old = UB.run_unified_exit_backtest(candles_u, "zzfib", {}, old_cfg["config"], meta_u)
    check("E: تشغيل موحد ثابت — لا compounding_audit في summary",
          "compounding_audit" not in ru_old["summary"])
    check("E: تشغيل موحد ثابت — لا position_size_semantics",
          "position_size_semantics" not in ru_old["summary"]["exit_strategy"])
    check("E: تشغيل موحد ثابت — exit_summary.capital بمفاتيح تاريخية",
          "final_equity_usd" not in ru_old["summary"]["exit_summary"]["capital"])

    nb, errs_nb = UB.validate_exit_block(
        "zzfib", None,
        {"position_sizing": "percent_of_equity", "position_size_pct": 1.0,
         "take_profit_pct": 5.0, "dca1_trigger_pct": 3.0, "dca2_trigger_pct": 5.0,
         "max_entries": 3})
    check("E: validate_exit_block يقبل الوضع التراكمي", errs_nb == [])

    ru = UB.run_unified_exit_backtest(candles_u, "zzfib", {}, nb["config"], meta_u)
    s = ru["summary"]
    esv = s["exit_strategy"]
    tr = s["exit_trades"]
    check("E: config_effective يصدّي الوضع والنسبة",
          esv["config_effective"].get("position_sizing") == "percent_of_equity"
          and esv["config_effective"].get("position_size_pct") == 1.0)
    check("E: position_size_semantics نص عربي بالبذرة الجذرية",
          "الوضع التراكمي" in esv.get("position_size_semantics", "")
          and "10000" in esv.get("position_size_semantics", ""))
    check("E: compounding_audit في summary (نمط math_audit)",
          s.get("compounding_audit", {}).get("consistent") is True)
    check("E: exit_summary.capital موسع",
          all(k in s["exit_summary"]["capital"] for k in
              ("final_equity_usd", "equity_growth_pct", "account_liquidated",
               "initial_capital_usd", "dust_floored_entries", "position_sizing")))
    check("E: أول دورة = 1٪ × بذرة الجذر 10000 = 100$",
          bool(tr) and abs(tr[0]["entries"][0]["usd"] - 100.0) <= 0.01,
          f"{tr[0]['entries'][0]['usd'] if tr else None}")
    check("E: equity_usd في منحنى exit_summary",
          all("equity_usd" in p for p in s["exit_summary"]["equity_curve"]))

    meta_seed2 = dict(meta_u, initial_capital=50000.0)
    ru2 = UB.run_unified_exit_backtest(candles_u, "zzfib", {}, nb["config"], meta_seed2)
    tr2 = ru2["summary"]["exit_trades"]
    check("E: بذرة 50000$ → أول دورة 500$ (الجذر يحكم)",
          bool(tr2) and abs(tr2[0]["entries"][0]["usd"] - 500.0) <= 0.01,
          f"{tr2[0]['entries'][0]['usd'] if tr2 else None}")

    direct = NEW.run_exit_backtest(candles_u, NEW.extract_entries_zzfib(fake_zzfib("zzfib", candles_u)),
                                   old_cfg["config"])
    dpnl = direct["summary"]["pnl"]
    # ✅ تصحيح مرجع الفحص: المقارنة للوضع الثابت (ru_old) لا التراكمي (s)
    # — الفحص الأصلي قارن تشغيل التراكمي بالمباشر الثابت فخالف اسمه.
    check("E: المسار الموحد الثابت == المحرك المباشر (pnl مطابق)",
          abs(float(ru_old["summary"]["total_pnl"]) - float(dpnl["total_usd"])) < 0.01,
          f"موحد={ru_old['summary']['total_pnl']} مباشر={dpnl['total_usd']}")
finally:
    _es._run_strategy = _orig_run_strategy

print("\n" + "=" * 78)
print(f"النتيجة: {PASS} نجح · {FAIL} فشل · الإجمالي {PASS + FAIL}")
if FAILURES:
    print("\nالإخفاقات:")
    for f in FAILURES:
        print("  ✗", f)
    sys.exit(1)
print("R66 OK — كل الفحوصات ناجحة")
