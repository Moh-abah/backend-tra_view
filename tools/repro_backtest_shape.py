#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R77-FIX reproduction: the EXACT server failure of #10000616.

Simulates the backtest pipeline DataFrame shape that reaches the mom engine:
engine1._normalize_candle_index drops the `time` column and sets a DatetimeIndex
→ columns = [open, high, low, close, volume], NO time column.

Before fix: osc_* all None, gate all False, s1/s2/s3 NOT gated (baseline trades).
"""
import sys, json, io
sys.path.insert(0, '/home/z/my-project/trading-system/zone-exit-ltf/runtime')
import pandas as pd

RUNTIME = '/home/z/my-project/trading-system/zone-exit-ltf/runtime'
DATA = '/home/z/my-project/trading-system/zone-exit-ltf/data/MMTUSDT_15m.json'
PAYLOAD = '/home/z/my-project/trading-system/qmom1-mmt-test/payload_qmom1_mmt_10000604.json'

candles = json.load(io.open(DATA, encoding='utf-8'))
payload = json.load(io.open(PAYLOAD, encoding='utf-8'))
ind_params = payload['strategy_config']['indicators'][0]['params']

# ---- build the backtest-shaped DataFrame (as engine1 hands it to strategy engine)
df = pd.DataFrame([{
    'open': float(c['open']), 'high': float(c['high']),
    'low': float(c['low']), 'close': float(c['close']),
    'volume': float(c['volume']),
} for c in candles])
df.index = pd.DatetimeIndex(
    pd.to_datetime([c['time'] for c in candles], unit='ms', utc=True), name='time')
print(f"DataFrame: shape={df.shape}, columns={list(df.columns)}, "
      f"index type={type(df.index).__name__}, has time col: {'time' in df.columns}")

from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema_mom import (
    zigzag_fib_e2e_trendy_quantum_ema_mom,
)

res = zigzag_fib_e2e_trendy_quantum_ema_mom(df, **ind_params)
series = res['series']
n = len(candles)

def cnt_true(k):
    v = series.get(k) or []
    return sum(1 for x in v if x is not None and float(x) > 0)

def cnt_nonnull(k):
    v = series.get(k) or []
    return sum(1 for x in v if x is not None)

print()
print("=== OSC SECTION (engine echo) ===")
osc = res.get('osc') or {}
print("warnings:", json.dumps(osc.get('warnings') or [], ensure_ascii=False)[:600])
print("warning_codes:", osc.get('warning_codes'))
print("counts:", json.dumps(osc.get('counts') or {}, ensure_ascii=False))
print("base_tf (section):", osc.get('base_tf'), "| n:", osc.get('n'))
for inst in (osc.get('instances') or [])[:7]:
    print(f"  inst {inst.get('id')}: available={inst.get('available')} code={inst.get('code')} why={inst.get('why')}")

print()
print("=== SERIES ===")
for k in ('zzfetqem_entry', 'zzfetqem_entry_s1', 'zzfetqem_entry_s2', 'zzfetqem_entry_s3'):
    print(f"{k:>28}: >0 count = {cnt_true(k)}")
for k in ('zzfetqem_osc_macd_4h_12_26_4_line', 'zzfetqem_osc_rsi_1h_14_14_value',
          'zzfetqem_osc_rsi_1d_10_14_value'):
    print(f"{k:>28}: non-null = {cnt_nonnull(k)} / {n}")
print(f"{'zzfetqem_osc_gate':>28}: non-null = {cnt_nonnull('zzfetqem_osc_gate')} / {n}")
print(f"{'zzfetqem_entry_iblocked_s1':>28}: >0 count = {cnt_true('zzfetqem_entry_iblocked_s1')}")
print(f"{'zzfetqem_ema_21':>28}: non-null = {cnt_nonnull('zzfetqem_ema_21')} / {n}")
