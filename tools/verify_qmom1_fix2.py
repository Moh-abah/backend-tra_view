#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R78-FIX2 verification — «الدمج فقط إضافة» (pure-addition drawing contract).

Checks:
L1  Engine: zzfetqe_* family (78) present AND each value bit-identical to the
    zzfetqem_* pre-gate mirror (same in-memory object — pure alias).
L2  Aggregates: zigzag_fib_e2e_trendy_quantum_ema (raw 0/1, 46 ones)
    + zigzag_fib_e2e_trendy_quantum_ema_mom (gated 0/1, 11 ones).
L3  Gate behavior unchanged: counts 46 / 11 / 35.
L4  columns_for_configs: 297 ind_* columns (78 zzfetqe + 108 zzfetqem
    + 62 zzfetq + 47 zzfet + 2 aggregates).
L5  Identity mode (no template): zzfetqe_* + zzfetqem_* == base engine
    bit-identical, gate open, aggregates equal.
V1  (live) POST the #10000604-identical QMOM1 payload, poll to done.
V2  (live) chart-data candles: ind_zzfetqe_ema_21..500 present with REAL
    values; ind_zigzag_* aggregates present; ind_zzfetqem_* present;
    trades == 11; momentum_gate.counts == 46/11/35.
"""
import sys, os, json, io, time, urllib.request

RUNTIME = os.environ.get('QMOM_RUNTIME',
    '/home/z/my-project/trading-system/qmom1-fix/runtime')
SERVER = os.environ.get('QMOM_SERVER', 'http://161.97.73.254:8000')
DATA = os.environ.get('QMOM_DATA',
    '/home/z/my-project/trading-system/zone-exit-ltf/data/MMTUSDT_15m.json')
PKG = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(PKG, '..', 'payloads', 'payload_qmom1_mmt_10000604.json')

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), "|", name,
          ("| " + str(detail)) if detail else "")

# ---------------- local battery ----------------
def local_battery():
    sys.path.insert(0, RUNTIME)
    import pandas as pd
    candles = json.load(io.open(DATA, encoding='utf-8'))
    payload = json.load(io.open(PAYLOAD, encoding='utf-8'))
    params = payload['strategy_config']['indicators'][0]['params']

    df = pd.DataFrame([{
        'open': float(c['open']), 'high': float(c['high']),
        'low': float(c['low']), 'close': float(c['close']),
        'volume': float(c['volume']),
    } for c in candles])
    df.index = pd.DatetimeIndex(
        pd.to_datetime([c['time'] for c in candles], unit='ms', utc=True),
        name='time')

    from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema_mom import (
        zigzag_fib_e2e_trendy_quantum_ema_mom as mom)
    res = mom(df, **params)
    s = res['series']
    qee = [k for k in s if str(k).startswith('zzfetqe_')]
    qem = [k for k in s if str(k).startswith('zzfetqem_')]
    check("L1 عائلة zzfetqe_* مستعادة (78)", len(qee) == 78, len(qee))
    GATED = {'zzfetqem_entry', 'zzfetqem_entry_s1', 'zzfetqem_entry_s2',
             'zzfetqem_entry_s3'}
    bad = [k for k in qee
           if 'zzfetqem_' + k[len('zzfetqe_'):] not in GATED
           and s[k] is not s['zzfetqem_' + k[len('zzfetqe_'):]]]
    check("L1b كل zzfetqe_X = zzfetqem_X (نفس الكائن — إضافة صرفة)", not bad, bad[:3])
    agg_r = s.get('zigzag_fib_e2e_trendy_quantum_ema') or []
    agg_f = s.get('zigzag_fib_e2e_trendy_quantum_ema_mom') or []
    check("L2a المجمّع الخام 0/1 بطول n", len(agg_r) == len(candles)
          and set(map(float, agg_r)) <= {0.0, 1.0})
    check("L2b المجمّع النهائي 0/1 بطول n", len(agg_f) == len(candles)
          and set(map(float, agg_f)) <= {0.0, 1.0})
    check("L2c المجمّع الخام = 46 دخولاً خاماً",
          sum(1 for v in agg_r if v == 1.0) == 46)
    check("L2d المجمّع النهائي = 11 بعد البوابة",
          sum(1 for v in agg_f if v == 1.0) == 11)
    counts = ((res.get('osc') or {}).get('counts') or {})
    check("L3 عدادات البوابة 46/11/35",
          counts == {'quantum_ema_entries': 46, 'final_entries': 11,
                     'osc_blocked_entries': 35}, counts)

    from app.services.indicators.overlay_columns import columns_for_configs
    class Cfg:
        def __init__(self, p):
            self.name = 'zigzag_fib_e2e_trendy_quantum_ema_mom'
            self.params = p
            self.enabled = True
    cols = columns_for_configs(df, [Cfg(params)])
    check("L4 عقد الشارت 297 عمود مؤشر", len(cols) == 297, len(cols))
    ema_ok = all(('ind_zzfetqe_ema_%d' % L) in cols for L in
                 (21, 50, 100, 200, 350, 500))
    check("L4b خطوط EMA الستة ind_zzfetqe_ema_* في العقد", ema_ok)
    agg_ok = ('ind_zigzag_fib_e2e_trendy_quantum_ema' in cols
              and 'ind_zigzag_fib_e2e_trendy_quantum_ema_mom' in cols)
    check("L4c العمودان المجمّعان ind_zigzag_* في العقد", agg_ok)

    # identity mode (params normalized exactly like the production path —
    # config_to_overlay_params drops touch_level for both engines alike)
    from app.services.indicators.overlay_columns import config_to_overlay_params
    _conv = config_to_overlay_params({
        'name': 'zigzag_fib_e2e_trendy_quantum_ema_mom',
        'params': {k: v for k, v in params.items()
                   if k not in ('osc_instances', 'osc_conditions')},
    }) or {}
    base_params = (_conv.get('zzfib_e2e_trendy_quantum_ema_mom') or {})
    from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
        zigzag_fib_e2e_trendy_quantum_ema as base)
    rm = mom(df, **dict(base_params))
    rb = base(df, **dict(base_params))
    sb, sm = rb['series'], rm['series']
    vbad = [k for k, v in sb.items() if str(k).startswith('zzfetqe_')
            and (sm.get(k) != v
                 or sm.get('zzfetqem_' + str(k)[len('zzfetqe_'):]) != v)]
    check("L5 وضع الهوية: zzfetqe_* + zzfetqem_* = الأساس بت-بت", not vbad, vbad[:3])
    check("L5b وضع الهوية: المجمّعان متساويان (بوابة مفتوحة)",
          sm.get('zigzag_fib_e2e_trendy_quantum_ema')
          == sm.get('zigzag_fib_e2e_trendy_quantum_ema_mom'))

# ---------------- live battery ----------------
def _get(url, timeout=90):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())

def live_battery():
    payload = json.load(io.open(PAYLOAD, encoding='utf-8'))
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        SERVER + '/api/v1/backtest1/run', data=body,
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=90) as r:
        sub = json.loads(r.read().decode())
    tid = sub.get('task_id')
    print("task:", tid)
    for _ in range(80):
        time.sleep(15)
        st = _get(SERVER + '/api/v1/backtest1/tasks/' + str(tid))
        if st.get('state') in ('SUCCESS', 'FAILURE'):
            break
    check("V1 المهمة اكتملت بنجاح", st.get('state') == 'SUCCESS',
          st.get('state'))
    if st.get('state') != 'SUCCESS':
        return
    s = st.get('summary_stats') or {}
    check("V1b الصفقات = 11 (البوابة تعمل)", s.get('total_trades') == 11, s)
    bid = st.get('backtest_id')
    cd = _get(SERVER + '/api/v1/backtest1/%s/chart-data' % bid, timeout=560)
    sym = cd.get('chart_data_by_symbol', {}).get('MMTUSDT', {})
    vc = sym.get('visual_candles') or []
    keys = set()
    for c in vc[:300]:
        keys.update(c.keys())
    ema = [k for k in keys if k.startswith('ind_zzfetqe_ema_')]
    want = ('ind_zzfetqe_ema_21', 'ind_zzfetqe_ema_50',
            'ind_zzfetqe_ema_100', 'ind_zzfetqe_ema_200',
            'ind_zzfetqe_ema_350', 'ind_zzfetqe_ema_500')
    check("V2a خطوط EMA الستة ind_zzfetqe_ema_* موجودة",
          all(w in keys for w in want), ema)
    nn = sum(1 for c in vc if c.get('ind_zzfetqe_ema_21') is not None)
    check("V2b قيم EMA حقيقية غير فارغة", nn > len(vc) * 0.9, f"{nn}/{len(vc)}")
    check("V2c العمود المجمّع الخام موجود",
          'ind_zigzag_fib_e2e_trendy_quantum_ema' in keys)
    check("V2d العمود المجمّع الجديد موجود",
          'ind_zigzag_fib_e2e_trendy_quantum_ema_mom' in keys)
    qe = [k for k in keys if k.startswith('ind_zzfetqe_')]
    qem = [k for k in keys if k.startswith('ind_zzfetqem_')]
    check("V2e عائلة الكمومية-EMA الكاملة (78)",
          len(qe) == 78, len(qe))
    check("V2f عائلة الزخم الكاملة (108)", len(qem) == 108, len(qem))
    g1 = sum(1 for c in vc
             if (c.get('ind_zigzag_fib_e2e_trendy_quantum_ema') or 0) > 0)
    g2 = sum(1 for c in vc
             if (c.get('ind_zigzag_fib_e2e_trendy_quantum_ema_mom') or 0) > 0)
    check("V2g المجمّع الخام = 46 شمعة إشارة",
          g1 == 46, g1)
    check("V2h المجمّع النهائي = 11", g2 == 11, g2)


if __name__ == '__main__':
    try:
        local_battery()
    except Exception as e:
        check("L-battery exception", False, repr(e))
    if '--live' in sys.argv:
        try:
            live_battery()
        except Exception as e:
            check("V-battery exception", False, repr(e))
    print()
    print(f"===== PASS {len(PASS)} / FAIL {len(FAIL)} =====")
    sys.exit(1 if FAIL else 0)
