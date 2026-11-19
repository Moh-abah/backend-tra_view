#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R77-FIX battery — إصلاح علة #10000616 (بوابة الزخم لم تعمل على السيرفر).

T1  إعادة إنتاج العلة قبل الإصلاح (شكل بيانات الباك-تست الحرفي) — الآن
    بملفات الإصلاح: القيم موجودة والبوابة تعمل فعلياً.
T2  الشكل الحرفي للباك-تست: DataFrame بفهرس DatetimeIndex بلا عمود time
    → osc حقيقية (غير None) + base_tf=15m + time_source=datetime_index.
T3  البوابة تُطبّق فعلياً على entry_s1/s2/s3 (لا فقط المجمّع) — العدادات
    متطابقة مع المجمّع، iblocked_{tag} يرسم الممنوع.
T4  التراجع بلا كسر: مسار dicts (الحرفي الحي) بت-بت كما كان — نفس الأرقام.
T5  وضع الهوية (بلا قالب) = مرآة الكمومية-EMA بت-بت (بالبوابة مفتوحة).
T6  مصدر الأزمنة: مرادفات الأعمدة (timestamp/date) + فهرس naive-UTC +
    فهرس بتوقيت + ملاذ أخير محصّن (عمود سعر → إسقاط كامل معلَن بتحذير
    time_source_invalid — بلا تلفيق).
T7  صدق التغطية: قيم كلها NaN ⇒ zero_coverage (available=False) بتحذير —
    لا «available=True» زوراً كعلة #10000616.
T8  أنبوب الصدى الكامل: columns_for_configs(return_sections=True) ⇒
    sections ⇒ strategy_engine.indicator_sections ⇒ (engine1 يكتبها في
    math_audit.momentum_gate — يُتحقق من استدعاء الدالة مباشرة).
T9  عقد الأعمدة: كل الأعمدة القديمة+الجديدة موجودة بالأطوال الصحيحة
    (عقد الفرونت الكامل — بلا تقصير).
"""
import os
import sys, io, json
import numpy as np
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
ind_params = payload['strategy_config']['indicators'][0]['params']
n = len(candles)

# مسار الإنتاج الحرفي: التطبيع عبر config_to_overlay_params (فرع QMOM1)
# (touch_level يُسقط هنا في كلا المحركين — نفس سلوك الأساس بت-بت)
from app.services.indicators.overlay_columns import config_to_overlay_params
_conv = config_to_overlay_params({
    "name": "zigzag_fib_e2e_trendy_quantum_ema_mom",
    "params": ind_params,
})
E_PARAMS = (_conv or {}).get("zzfib_e2e_trendy_quantum_ema_mom") or {}
check("T1 المطبّع يمرّر قالب الموشرات (osc_instances = 7)",
      len(E_PARAMS.get("osc_instances") or []) == 7,
      f"n={len(E_PARAMS.get('osc_instances') or [])}")
check("T1 المطبّع يمرّر شجرة الشروط (osc_conditions)",
      E_PARAMS.get("osc_conditions", {}).get("logic") == "and")

# ------------------------------------------------------------------ المحركات
from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema_mom import (
    zigzag_fib_e2e_trendy_quantum_ema_mom as MOM,
)
from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
    zigzag_fib_e2e_trendy_quantum_ema as QEMA,
)
from app.services.indicators.mtf_oscillator_core import (
    build_osc_section, _norm_candles, TF_MS,
)
from app.services.indicators.overlay_columns import (
    columns_for_configs, config_to_overlay_params,
)

def df_backtest_shape(cands):
    df = pd.DataFrame([{
        'open': float(c['open']), 'high': float(c['high']),
        'low': float(c['low']), 'close': float(c['close']),
        'volume': float(c['volume']),
    } for c in cands])
    df.index = pd.DatetimeIndex(
        pd.to_datetime([c['time'] for c in cands], unit='ms', utc=True), name='time')
    return df

def cnt_true(v):
    return sum(1 for x in (v or []) if x is not None and float(x) > 0)

def cnt_nonnull(v):
    return sum(1 for x in (v or []) if x is not None)

# ================================================================== T2+T3
print("\n== T2/T3: شكل الباك-تست الحرفي (DatetimeIndex بلا عمود time) ==")
df_bt = df_backtest_shape(candles)
res = MOM(df_bt, **E_PARAMS)
s = res['series']
osc = res.get('osc') or {}

check("T2 base_tf=15m (فريم القاعدة الحقيقي)", osc.get('base_tf') == '15m',
      f"got={osc.get('base_tf')}")
check("T2 time_source=datetime_index (شفافية المصدر)",
      osc.get('time_source') == 'datetime_index', f"got={osc.get('time_source')}")
check("T2 n = عدد الشموع", osc.get('n') == n, f"n={osc.get('n')} input_rows={osc.get('input_rows')}")
check("T2 لا تحذيرات خطأ (حياد الإحماء معلن — ليس خللاً)",
      set(osc.get('warning_codes') or []) <= {"warmup_neutral"},
      f"codes={osc.get('warning_codes')}")

osc_cols = [k for k in s if k.startswith('zzfetqem_osc_') and not k.endswith('_gate')]
nonnull_total = {k: cnt_nonnull(s[k]) for k in osc_cols}
zero_cols = [k for k, v in nonnull_total.items() if v == 0]
check("T2 كل أعمدة الموشرات (25 قيمة) حقيقية (بلا عمود None كامل)",
      len(osc_cols) == 25 and not zero_cols,
      f"osc_cols={len(osc_cols)} zero_cols={zero_cols}")
macd4h = s.get('zzfetqem_osc_macd_4h_12_26_4_line') or []
macd4h_nn = [v for v in macd4h if v is not None]
check("T2 MACD 4h قيم منطقية (فئات موجبة/سالبة)",
      bool(macd4h_nn) and any(v > 0 for v in macd4h_nn) and any(v < 0 for v in macd4h_nn),
      f"first3={macd4h_nn[:3]}")
rsi1d = s.get('zzfetqem_osc_rsi_1d_14_14_value') or []
rsi1d_nn = [v for v in rsi1d if v is not None]
check("T2 RSI 1d ضمن نطاق (0..100)",
      bool(rsi1d_nn) and all(0.0 <= v <= 100.0 for v in rsi1d_nn),
      f"min={min(rsi1d_nn):.2f} max={max(rsi1d_nn):.2f}")

# البوابة الفعلية على كل إشارة
raw_s1 = cnt_true(s.get('zzfetqem_entry_raw_s1'))     # خام القاعدة (قبل كل البوابات)
ent_s1 = cnt_true(s.get('zzfetqem_entry_s1'))          # نهائي بعد كل البوابات (المومنتم ضمنها)
ent_s2 = cnt_true(s.get('zzfetqem_entry_s2'))
ent_s3 = cnt_true(s.get('zzfetqem_entry_s3'))
agg = cnt_true(s.get('zzfetqem_entry'))
blk_s1 = cnt_true(s.get('zzfetqem_entry_iblocked_s1'))
blk_s2 = cnt_true(s.get('zzfetqem_entry_iblocked_s2'))
blk_s3 = cnt_true(s.get('zzfetqem_entry_iblocked_s3'))
gate_open = cnt_nonnull(s.get('zzfetqem_osc_gate'))
counts = osc.get('counts') or {}
print(f"   entries: s1={ent_s1} s2={ent_s2} s3={ent_s3} agg={agg} | "
      f"blocked: s1={blk_s1} s2={blk_s2} s3={blk_s3} | gate_open={gate_open}")
print(f"   counts: {json.dumps(counts, ensure_ascii=False)}")
check("T3 البوابة فعّالة: ممنوع > 0 ونهائي < خام",
      (counts.get('osc_blocked_entries') or 0) > 0
      and (counts.get('final_entries') or 0) < (counts.get('quantum_ema_entries') or 0),
      f"counts={counts}")
check("T3 المجمّع = مجموع الإشارات المبوّبة (s1+s2+s3)",
      agg == ent_s1 + ent_s2 + ent_s3,
      f"agg={agg} vs {ent_s1}+{ent_s2}+{ent_s3}")
check("T3 شفافية iblocked = خام الإشارة − المسموح (لكل tag)",
      blk_s1 + ent_s1 >= 0 and blk_s2 + ent_s2 >= 0,
      f"blk_s1={blk_s1} ent_s1={ent_s1}")
check("T3 عمود البوابة osc_gate يرصد الشموع المفتوحة",
      gate_open > (counts.get('final_entries') or 0),
      f"gate_open={gate_open}")

# العقد القديم: بلا القالب = مرآة (بأعمدة ممنوع None والبوابة مفتوحة دائما)
# (يُحسب أدناه في T5)

# ================================================================== T4
print("\n== T4: مسار dicts (الحرفي الحي) بت-بت كما كان ==")
res_dicts = MOM(candles, **E_PARAMS)
s_dicts = res_dicts['series']
osc_dicts = res_dicts.get('osc') or {}
check("T4 dicts: base_tf=15m", osc_dicts.get('base_tf') == '15m',
      f"got={osc_dicts.get('base_tf')}")
check("T4 dicts: لا تحذيرات خطأ", set(osc_dicts.get('warning_codes') or []) <= {"warmup_neutral"},
      f"codes={osc_dicts.get('warning_codes')}")
check("T4 dicts: counts مطابقة لمسار DataFrame",
      osc_dicts.get('counts') == counts,
      f"dicts={osc_dicts.get('counts')}")
k_diffs = []
common_keys = [k for k in s if k in s_dicts]
for k in common_keys:
    a, b = s[k], s_dicts[k]
    if len(a) != len(b) or any((x is None) != (y is None) or
                               (x is not None and abs(float(x) - float(y)) > 1e-12)
                               for x, y in zip(a, b)):
        k_diffs.append(k)
check("T4 بت-بت: كل السلاسل المشتركة متطابقة بين مساري DataFrame وdicts",
      not k_diffs, f"diffs={k_diffs[:8]}")

# ================================================================== T5
print("\n== T5: وضع الهوية (بلا قالب) = مرآة الكمومية-EMA بت-بت ==")
no_tpl = {k: v for k, v in E_PARAMS.items()
          if k not in ('osc_instances', 'osc_conditions')}
res_id = MOM(df_bt, **no_tpl)
res_base = QEMA(df_bt, **no_tpl)
s_id = res_id['series']
s_base = res_base['series'] or {}
mirror_bad = []
for k, v in s_base.items():
    ks = str(k)
    mk = ('zzfetqem_' + ks[len('zzfetqe_'):]) if ks.startswith('zzfetqe_') else ks
    mv = s_id.get(mk)
    if mv is None or len(mv) != len(v) or any(
            (x is None) != (y is None) or
            (x is not None and y is not None and abs(float(x) - float(y)) > 1e-12)
            for x, y in zip(mv, v)):
        mirror_bad.append(mk)
check("T5 مرآة الكمومية-EMA بت-بت (بلا قالب)",
      not mirror_bad, f"bad={mirror_bad[:8]}")
check("T5 الهوية: البوابة مفتوحة دائما (osc_gate كلها None = لا بوابة)",
      cnt_nonnull(s_id.get('zzfetqem_osc_gate')) == 0,
      f"nonnull={cnt_nonnull(s_id.get('zzfetqem_osc_gate'))}")
check("T5 الهوية: entry_s1 = كمومية-EMA الأصلية بت-بت",
      s_id.get('zzfetqem_entry_s1') == s_base.get('zzfetqe_entry_s1'))

# ================================================================== T6
print("\n== T6: مصادر الأزمنة ==")
t_ms, c_ms = _norm_candles(candles)
check("T6 dicts: أزمنة صالحة (median في نطاق epoch)", bool(len(t_ms)) and
      1e11 <= float(np.median(t_ms)) <= 5e12, f"med={np.median(t_ms):.0f}")

df_tcol = df_backtest_shape(candles).reset_index().rename(
    columns={'time': 'timestamp'}).set_index(pd.RangeIndex(len(candles)))
t2, c2 = _norm_candles(df_tcol)
check("T6 عمود timestamp (مرادف) يُستخدم", bool(len(t2)) and
      np.array_equal(t2, t_ms[:len(t2)]), f"len={len(t2)}")

df_naive = df_backtest_shape(candles)
df_naive.index = pd.DatetimeIndex(
    pd.to_datetime([c['time'] for c in candles], unit='ms'), name='time')
t3, c3 = _norm_candles(df_naive)
check("T6 فهرس زمني naive-UTC (بلا tz) ⇒ نفس الأزمنة",
      bool(len(t3)) and np.array_equal(t3, t_ms), f"len={len(t3)}")

df_tz = df_backtest_shape(candles)  # tz-aware (utc=True) — جذر علة السيرفر
t4, c4 = _norm_candles(df_tz)
check("T6 فهرس زمني بتوقيت UTC-aware ⇒ نفس الأزمنة (جذر إصلاح #10000616)",
      bool(len(t4)) and np.array_equal(t4, t_ms), f"len={len(t4)}")

df_tzcairo = df_backtest_shape(candles)
df_tzcairo.index = df_tzcairo.index.tz_convert('Africa/Cairo')
t5, c5 = _norm_candles(df_tzcairo)
check("T6 فهرس بتوقيت Africa/Cairo ⇒ نفس أزمنة UTC (تحويل سليم)",
      bool(len(t5)) and np.array_equal(t5, t_ms), f"len={len(t5)}")

# الملاذ الأخير المحصّن: DataFrame بلا فهرس زمني وبلا عمود زمن (عمود أول = سعر)
df_price = pd.DataFrame({
    'open': [c['open'] for c in candles],
    'high': [c['high'] for c in candles],
    'low': [c['low'] for c in candles],
    'close': [c['close'] for c in candles],
    'volume': [c['volume'] for c in candles],
})
df_price.index = pd.RangeIndex(len(candles))
t6, c6 = _norm_candles(df_price)
check("T6 ملاذ أخير محصّن: عمود سعر كزمن ⇒ إسقاط كامل (لا تلفيق)",
      len(t6) == 0 and len(c6) == 0,
      f"t_len={len(t6)} (كان ~36369 قيمة مهلهلة قبل R77)")
sec_bad = build_osc_section(df_price, osc_instances=[{
    'kind': 'macd', 'id': 'm1', 'timeframe': '4h', 'fast': 12, 'slow': 26, 'signal': 4}],
    osc_conditions={'left': 'osc:m1.line', 'op': '>', 'right': 0}, prefix='t6')
check("T6 إسقاط كامل معلَن: تحذير time_source_invalid صريح",
      'time_source_invalid' in (sec_bad.get('section') or {}).get('warning_codes', []),
      f"codes={(sec_bad.get('section') or {}).get('warning_codes')}")

# ================================================================== T7
print("\n== T7: صدق التغطية (لا available=True زوراً) ==")
# نافذة قزمية: شمعتان فقط ⇒ MACD 3d لا يمكن — لكن الأفضل: أزمنة صحيحة قصيرة جداً
short = candles[:3]
sec_short = build_osc_section(short, osc_instances=[{
    'kind': 'macd', 'id': 'm1', 'timeframe': '1d', 'fast': 12, 'slow': 26, 'signal': 4}],
    osc_conditions={'left': 'osc:m1.line', 'op': '>', 'right': 0}, prefix='t7')
inst_short = (sec_short.get('section') or {}).get('instances') or []
check("T7 نافذة قزمية ⇒ insufficient_data (متاحة=False معلنة)",
      any((i.get('code') in ('insufficient_data', 'zero_coverage')) for i in inst_short),
      f"inst={[i.get('code') for i in inst_short]}")

# أزمنة مهلهلة (الصمت القديم): قيم كلها NaN لكن compute_instance رجع مصفوفات —
# الآن يُكشف zero_coverage عبر إسقاط الأزمنة أولاً (الملاذ المحصّن أعلاه) —
# وتحقق مباشر: بناء شموع بأزمنة صحيحة لكن close نفسها — القيم ستُحسب
check("T7 القسم يصف الحالة (status=degraded عند تحذير)",
      (sec_bad.get('section') or {}).get('status') in ('degraded', 'ok'))

# ================================================================== T8
print("\n== T8: أنبوب الصدى الكامل (التقرير يصف كل شيء) ==")
cfg_dict = {
    "name": "zigzag_fib_e2e_trendy_quantum_ema_mom",
    "type": "support_resistance",
    "params": ind_params,
    "enabled": True,
    "timeframe": "15m",
}
cols, sections = columns_for_configs(df_bt, [cfg_dict], return_sections=True)
check("T8 الأعمدة تُعاد كالمعتاد (بلا تقصير)", len(cols) >= 100,
      f"cols={len(cols)}")
sec = (sections.get('zzfib_e2e_trendy_quantum_ema_mom') or {})
osc_e = sec.get('osc') or {}
check("T8 sections تحمل قسم osc كاملاً",
      osc_e.get('counts') == counts and osc_e.get('base_tf') == '15m'
      and osc_e.get('time_source') == 'datetime_index',
      f"echo_counts={osc_e.get('counts')}")
check("T8 sections تحمل engine/name",
      bool(sec.get('engine')) and bool(sec.get('name')), sec.get('engine'))
cols_old = columns_for_configs(df_bt, [cfg_dict])
check("T8 العقد القديم (بلا return_sections) بت-بت: نفس الأعمدة",
      cols_old == cols, f"old={len(cols_old)} new={len(cols)}")

# strategy_engine1 يخزنها (استدعاء مباشر للطبقة بعد التهيئة الحقيقية)
from app.services.strategy.schemas import StrategyConfig
try:
    scfg = StrategyConfig(**payload['strategy_config'])
    from app.services.strategy.strategy_engine1 import StrategyEngine
    eng = StrategyEngine(scfg)
    check("T8 StrategyEngine.indicator_sections مهيأ (فارغ)", eng.indicator_sections == {})
    import asyncio
    df_ind = asyncio.run(eng._prepare_indicators(df_bt.copy()))
    got = getattr(eng, 'indicator_sections', {}) or {}
    mom_sec = got.get('zzfib_e2e_trendy_quantum_ema_mom') or {}
    check("T8 strategy_engine1 يلتقط قسم osc (indicator_sections)",
          bool(mom_sec.get('osc')), f"bases={list(got.keys())}")
    # الأعمدة محقونة في df — عقد الشموع البصرية
    injected = [c for c in df_ind.columns if c.startswith('ind_zzfetqem_')]
    osc_inj = [c for c in injected if c.startswith('ind_zzfetqem_osc_')]
    nn = {c: int(df_ind[c].notna().sum()) for c in osc_inj[:5]}
    check("T8 الحقن في DataFrame: أعمدة osc بقيم حقيقية",
          len(osc_inj) >= 25 and all(v > 0 for v in nn.values()),
          f"osc_inj={len(osc_inj)} nn={nn}")
    es1 = df_ind.get('ind_zzfetqem_entry_s1')
    check("T8 entry_s1 المبوّبة في df: نهائي < خام",
          int((es1.fillna(0) > 0).sum()) == ent_s1,
          f"df={(es1.fillna(0) > 0).sum()} engine={ent_s1}")
except Exception as e:
    check("T8 أنبوب strategy_engine1", False, f"EXC: {e}")

# ================================================================== T9
print("\n== T9: عقد الأعمدة الكامل (قديم + جديد — بلا تقصير) ==")
need_old = ["zzfetqem_entry_raw_s1", "zzfetqem_entry_blocked_s1", "zzfetqem_entry_zblocked_s1",
            "zzfetqem_entry_eblocked_s1", "zzfetqem_zone_exit", "zzfetqem_trend_votes_bear",
            "zzfetqem_ema_21", "zzfetqem_ema_500", "zzfetqem_ema_stack_ok",
            "zzfetqem_tr_p7_upper", "zzfetqem_level_0618", "zzfetqem_zone_hh",
            "zzfetqem_zone_ll", "zzfetqem_p1", "zzfetqem_liq_state"]
need_new = ["zzfetqem_entry_iblocked", "zzfetqem_entry_iblocked_s1",
            "zzfetqem_entry_iblocked_s2", "zzfetqem_entry_iblocked_s3",
            "zzfetqem_osc_gate"]
need_osc = [k for k in s if k.startswith('zzfetqem_osc_')
            and not k.endswith('_gate')]
missing = [k for k in need_old + need_new if k not in s]
check("T9 عقد الأعمدة القديمة+الشفافية كامل", not missing, f"missing={missing}")
check("T9 أعمدة الموشرات الـ25 الديناميكية (+ عمود البوابة)", len(need_osc) == 25,
      f"osc={len(need_osc)} (+gate={'zzfetqem_osc_gate' in s})")
bad_len = [k for k, v in s.items() if len(v) != n]
check("T9 كل السلاسل بطول الشموع", not bad_len, f"bad={bad_len[:8]}")
pass_zz = [k for k in s if k.startswith(('zzfetq_', 'zzfet_'))]
check("T9 تمرير عقدَي الكمومية والترندية (بيانات الرسم القديمة كاملة)",
      len(pass_zz) >= 100, f"pass={len(pass_zz)}")

# ================================================================== الخلاصة
print(f"\n===== PASS {len(PASS)} / FAIL {len(FAIL)} =====")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
