# -*- coding: utf-8 -*-
"""
فحص السببية على الكود المصحح — next_open الحرفي (نفس مسار run_round32_realtest):
لكل صفقة ترندية: (أ) سعر الدخول = فتح شمعة الدخول بالضبط
                (ب) شمعة الإشارة = الشمعة السابقة مباشرة وعندها حدث مسموح s1/s2/s3
                (ج) entry_time − signal_time = timeframe_ms
"""
import copy, json, sys, asyncio
sys.path.insert(0, "/home/z/my-project/user-project")
import pandas as pd

from app.backtest.engine1 import BacktestEngine
from app.backtest.schemas import BacktestConfig
from app.services.strategy.presets import ZLF_E2E_TRENDY_TRIPLE_SIGNAL
from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy

sys.path.insert(0, "/home/z/my-project/download/ROUND23-REAL-TEST")
from zlf_fetch import klines_to_df  # noqa: E402

raw = json.load(open("/home/z/my-project/tmp_drive/round32_fix/btc_candles_raw.json"))
TF_MS = 60000
df, forming = klines_to_df(raw, TF_MS, raw[-1][0] + TF_MS)
print("df:", df.shape)


class StubDataService:
    def __init__(self, df_):
        self._df = df_
    async def get_historicallastvirsion(self, **kw):
        return self._df.copy()


def asyncio_run(coro):
    return asyncio.run(coro)


start = df.index.min().strftime("%Y-%m-%d")
end = (df.index.max() + pd.Timedelta(minutes=1)).strftime("%Y-%m-%d")
cfg = BacktestConfig(
    name="causality33:BTCUSDT:1m",
    symbols=["BTCUSDT"],
    timeframe="1m",
    market="crypto",
    start_date=start,
    end_date=end,
    initial_capital=10000.0,
    position_size_percent=1.0,
    fill_model="next_open",
    tz_offset_minutes=0,
    strategy_config=copy.deepcopy(ZLF_E2E_TRENDY_TRIPLE_SIGNAL["strategy_config"]),
    stop_loss_percent=2.0,
    take_profit_percent=99.0,
)
engine = BacktestEngine(StubDataService(df))
result = asyncio_run(engine.run_backtest(cfg))
trades = list(getattr(result, "trades", None) or [])
print("trades:", len(trades))

# أحداث الإشارة المسموحة من محرك الاستراتيجية على نفس الشموع
trendy = zigzag_fib_e2e_trendy(df, mode="luxalgo", length=100)
s = trendy["series"]
admitted_ev = set()
for k in ("zzfet_entry_s1", "zzfet_entry_s2", "zzfet_entry_s3"):
    for i, v in enumerate(s[k]):
        if float(v or 0) > 0:
            admitted_ev.add(i)
print("admitted events:", len(admitted_ev))

idx = list(df.index)
t2i = {int(t.value // 10**6): i for i, t in enumerate(idx)}

ok_a = ok_b = ok_c = 0
fails = []
for tr in trades:
    et_attr = getattr(tr, "entry_time", None)
    ep = float(getattr(tr, "entry_price", None))
    et_ms = int(pd.Timestamp(et_attr).value // 10**6) if not isinstance(et_attr, (int, float)) else int(et_attr)
    i = t2i.get(et_ms)
    if i is None:
        fails.append(("entry time not found", et_ms)); continue
    opn = float(df.iloc[i]["open"])
    if abs(ep - opn) < 1e-9:
        ok_a += 1
    else:
        fails.append(("entry!=open", et_ms, ep, opn))
    if i >= 1:
        if et_ms - int(idx[i - 1].value // 10**6) == TF_MS:
            ok_c += 1
        else:
            fails.append(("dt!=tf", et_ms))
        if (i - 1) in admitted_ev:
            ok_b += 1
        else:
            fails.append(("no admitted signal at prev bar", et_ms, i - 1))
print(f"\n(أ) دخول = فتح شمعة الدخول: {ok_a}/{len(trades)}")
print(f"(ب) إشارة مسموحة في الشمعة السابقة: {ok_b}/{len(trades)}")
print(f"(ج) فارق الزمن = tf_ms بالضبط: {ok_c}/{len(trades)}")
if fails:
    print("أمثلة إخفاق:", fails[:3])
verdict = ok_a == len(trades) and ok_b == len(trades) and ok_c == len(trades)
print("النتيجة:", "السببية سليمة 100% على الكود المصحح ✓" if verdict else "✗")
json.dump({"trades": len(trades), "ok_a": ok_a, "ok_b": ok_b, "ok_c": ok_c,
           "verdict": verdict, "fails": fails[:5]},
          open("/home/z/my-project/download/ROUND33-LOWER-PIVOT-FIX/evidence/realtest/causality_alignment.json", "w"))
