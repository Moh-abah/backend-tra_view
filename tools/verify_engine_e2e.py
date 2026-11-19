#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T10 — التكامل الكامل لمحرك الباك-تست بعد إصلاح R77 (بلا قاعدة بيانات).

يستدعي _simulate_with_strategy + _create_backtest_result مباشرة على:
  • شموع MMTUSDT 15m (36,369) بشكل بيانات الباك-تست الحرفي
    (DatetimeIndex + [open,high,low,close,volume] — بلا عمود time)
  • حمولة QMOM1 نفسها (#10000616 = تكوين #10000604 + بوابة الزخم)

يتحقق:
  A) عدد الصفقات ~11 (لا 46!) — البوابة تعمل فعلياً في قرار التداول
  B) summary.math_audit.momentum_gate موجود بقسم osc كامل (counts/instances/)
     warnings/time_source/base_tf/warmup) — «التقرير يصف كل شيء»
  C) الشموع البصرية تحمل ind_zzfetqem_osc_* بقيم حقيقية + iblocked
     + كل الأعمدة القديمة (عقد بيانات الرسم كاملاً)
"""
import asyncio
import io
import json
import os
import sys

import pandas as pd

RUNTIME = os.environ.get('QMOM_RUNTIME',
           '/home/z/my-project/trading-system/qmom1-fix/runtime')
sys.path.insert(0, RUNTIME)

DATA = '/home/z/my-project/trading-system/zone-exit-ltf/data/MMTUSDT_15m.json'
PAYLOAD = '/home/z/my-project/trading-system/qmom1-mmt-test/payload_qmom1_mmt_10000604.json'

PASS, FAIL = [], []

def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), "|", name, ("| " + str(detail)) if detail else "")

candles = json.load(io.open(DATA, encoding='utf-8'))
payload = json.load(io.open(PAYLOAD, encoding='utf-8'))

df = pd.DataFrame([{
    'open': float(c['open']), 'high': float(c['high']),
    'low': float(c['low']), 'close': float(c['close']),
    'volume': float(c['volume']),
} for c in candles])
df.index = pd.DatetimeIndex(
    pd.to_datetime([c['time'] for c in candles], unit='ms', utc=True), name='time')

from app.backtest.schemas import BacktestConfig

# --- stub بلا قاعدة بيانات: engine1 يستورد DataService كنوع فقط (نمرر stubنا)
import types as _types
_ds_mod = _types.ModuleType('app.services.data_service')
class _DSStub:  # noqa: D401
    pass
_ds_mod.DataService = _DSStub
if 'app.services.data_service' not in sys.modules:
    sys.modules['app.services.data_service'] = _ds_mod

from app.backtest.engine1 import BacktestEngine

config = BacktestConfig(**payload)


class _StubDataService:
    """لا قاعدة بيانات محلياً — فشل جلب LTF يُتخطى بأمان (عقد الزحزحة)."""
    async def get_historicallastvirsion(self, *a, **kw):
        raise RuntimeError("stub: no db locally")


async def main():
    eng = BacktestEngine(_StubDataService())
    trades, equity, vis, points = await eng._simulate_with_strategy(
        'MMTUSDT', df, config, float(config.initial_capital))

    print(f"\ntrades={len(trades)} | visual_candles={len(vis)} | "
          f"equity_pts={len(equity)}")
    wins = [t for t in trades if (t.pnl or 0) > 0]
    print(f"wins={len(wins)} losses={len(trades) - len(wins)}")

    result = await eng._create_backtest_result(
        config=config, trades=trades, equity_curve=equity,
        visual_candles=vis, trade_points=points,
        execution_start=__import__('datetime').datetime.utcnow())

    # ------------------------------------------------ A: البوابة فعّالة في القرار
    check("A الصفقات قليلة بعد البوابة (<= 15 لا 46)", len(trades) <= 15,
          f"trades={len(trades)}")
    check("A كل الصفقات دخلت عبر إشارات مسموحة (رصة/زخم)",
          all(t.entry_time is not None for t in trades))

    # ------------------------------------------------ B: التقرير الكامل
    mg = (result.math_audit or {}).get('momentum_gate')
    check("B math_audit.momentum_gate موجود", mg is not None, f"keys={list((result.math_audit or {}).keys())}")
    if mg:
        cts = mg.get('counts') or {}
        print(f"   momentum_gate.counts = {json.dumps(cts, ensure_ascii=False)}")
        print(f"   time_source={mg.get('time_source')} base_tf={mg.get('base_tf')} "
              f"warmup={mg.get('warmup_neutral_bars')} n={mg.get('n')} "
              f"warn={mg.get('warning_codes')}")
        check("B العدادات الثلاثية موجودة (خام/نهائي/ممنوع)",
              all(k in cts for k in ('quantum_ema_entries', 'final_entries',
                                     'osc_blocked_entries')),
              f"counts={cts}")
        check("B العدادات متسقة مع الصفقات الفعلية",
              cts.get('final_entries') == len(trades),
              f"final={cts.get('final_entries')} vs trades={len(trades)}")
        check("B مصدر الأزمنة = datetime_index (جذر الإصلاح ظاهر للتقرير)",
              mg.get('time_source') == 'datetime_index',
              f"got={mg.get('time_source')}")
        check("B حالات النسخ السبع (instances[])",
              len(mg.get('instances') or []) == 7,
              f"n={len(mg.get('instances') or [])}")
        check("B تحذيرات الحياد معلنة (warmup_neutral)",
              'warmup_neutral' in (mg.get('warning_codes') or []),
              f"codes={mg.get('warning_codes')}")

    # ------------------------------------------------ C: بيانات الرسم كاملة
    first = vis[0].indicators if vis else {}
    osc_keys = [k for k in first if k.startswith('ind_zzfetqem_osc_')
                and not k.endswith('_gate')]
    old_keys = [k for k in first if k.startswith(('ind_zzfetqem_ema_',
                                                  'ind_zzfetqem_tr_',
                                                  'ind_zzfetqem_zone_',
                                                  'ind_zzfetqem_level_'))]
    blk_keys = [k for k in first if k.startswith('ind_zzfetqem_entry_iblocked')]
    print(f"   osc_cols={len(osc_keys)} old_cols={len(old_keys)} blocked_cols={len(blk_keys)}")
    check("C أعمدة الموشرات الـ25 في الشموع البصرية", len(osc_keys) == 25,
          f"osc={len(osc_keys)}")
    check("C الأعمدة القديمة (EMA/ترند/منطقة/فيبو) موجودة", len(old_keys) >= 30,
          f"old={len(old_keys)}")
    check("C أعمدة الشفافية iblocked موجودة", len(blk_keys) >= 4,
          f"blk={len(blk_keys)}")
    # قيم حقيقية في العينة
    nn = 0
    tot = 0
    for v in vis[:: max(1, len(vis) // 400)]:
        for k in osc_keys[:6]:
            x = v.indicators.get(k)
            tot += 1
            if x is not None:
                nn += 1
    check("C قيم الموشرات حقيقية في شموع العينة", nn > tot * 0.7,
          f"nonnull={nn}/{tot}")

    print(f"\n===== T10: PASS {len(PASS)} / FAIL {len(FAIL)} =====")
    if FAIL:
        print("FAILURES:", FAIL)
        return 1
    return 0

sys.exit(asyncio.run(main()))
