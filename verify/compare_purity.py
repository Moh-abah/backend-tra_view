#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EBREAK1 فحص 1-2: الإضافة الصرفة بت-بت + صحة الأعمدة الجديدة على بيانات البطل."""
import pickle, sys

before = pickle.load(open("/tmp/ser_before.pkl", "rb"))
after = pickle.load(open("/tmp/ser_after.pkl", "rb"))
sb, sa = before["series"], after["series"]

def eq(a, b):
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x is None and y is None:
            continue
        if x is None or y is None:
            return False
        try:
            fx, fy = float(x), float(y)
        except (TypeError, ValueError):
            return x == y
        if fx != fy and not (fx != fx and fy != fy):
            return False
    return True

NEW = ["zzfetqe_ebreak_break", "zzfetqe_ebreak_ref_high",
       "zzfetqe_ebreak_ref_close", "zzfetqe_ebreak_drop_ok",
       "zzfetqe_ebreak_reclaim"]
fails = []
# 1) الإضافة الصرفة
for k, v in sb.items():
    if k not in sa:
        fails.append(f"MISSING after: {k}")
    elif not eq(v, sa[k]):
        fails.append(f"CHANGED: {k}")
print(f"[{'PASS' if not fails else 'FAIL'}] 1) الإضافة الصرفة: "
      f"{len(sb)} عموداً قائماً بت-بت بلا أي تغيير")
for f in fails[:10]:
    print("   ", f)

# 2) الأعمدة الجديدة
ok2 = all(k in sa for k in NEW)
print(f"[{'PASS' if ok2 else 'FAIL'}] 2) الأعمدة الخمسة الجديدة موجودة")
for k in NEW:
    if k not in sa:
        print("    MISSING:", k)

eb = after["ema_break"] or {}
cnt = eb.get("counts") or {}
print(f"    قسم ema_break: breaks={cnt.get('breaks')} armed_at_break="
      f"{cnt.get('armed_at_break')} reclaims={cnt.get('reclaims')} "
      f"line_source={eb.get('line_source')} drop_pct={eb.get('drop_pct')} "
      f"break_length={eb.get('break_length')}")

br = sa["zzfetqe_ebreak_break"]
rc = sa["zzfetqe_ebreak_reclaim"]
n_br = sum(1 for v in br if v and v > 0)
n_rc = sum(1 for v in rc if v and v > 0)
ok3 = n_br == cnt.get("breaks") and n_rc == cnt.get("reclaims") and n_rc > 0
print(f"[{'PASS' if ok3 else 'FAIL'}] 3) العدادات متسقة مع الأعمدة "
      f"(breaks={n_br} reclaims={n_rc})")

# 4) الدلالة: reclaim ⇒ drop_ok=1 عند نفس الشمعة و close>ref_high
rh, rcl, dk = (sa["zzfetqe_ebreak_ref_high"], sa["zzfetqe_ebreak_ref_close"],
               sa["zzfetqe_ebreak_drop_ok"])
sem = True
first = [i for i, v in enumerate(rc) if v and v > 0][:3]
for i in first:
    if not (dk[i] and rh[i] is not None):
        sem = False
print(f"[{'PASS' if sem else 'FAIL'}] 4) دلالة الاسترداد (أمثلة: {first}) "
      f"ref_high={ [round(rh[i],4) if rh[i] else None for i in first] }")

# 5) ref قيم فريدة داخل كل حلقة (تثبيت شمعة الكسر): تغيّر ref_high فقط عند break=1
chg = 0
prev = None
for i in range(len(rh)):
    cur = rh[i]
    if prev is None and cur is None:
        continue
    if (prev is None) != (cur is None) or (prev is not None and cur is not None and prev != cur):
        if not (br[i] and br[i] > 0):
            sem = False
            chg += 1
    prev = cur
print(f"[{'PASS' if chg == 0 else 'FAIL'}] 5) ref_high لا يتغير إلا عند شمعة كسر "
      f"(خروقات={chg})")

rc_br = sum(1 for i, v in enumerate(br) if v and v > 0 and rh[i] is not None)
print(f"    عينة أول ثلاث شموع كسر: bars={[i for i,v in enumerate(br) if v and v>0][:3]}")
sys.exit(1 if fails or not (ok2 and ok3 and sem) else 0)
