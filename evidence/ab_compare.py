#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مقارنة A/B — يجب صفر فروق في كل القيم عدا الأزمنة المُصححة (0 → صحيح)."""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OLD = json.load(open(os.path.join(ROOT, "ab_old.json")))
NEW = json.load(open(os.path.join(ROOT, "ab_new.json")))

TIME_KEYS = {"t1", "t2", "time", "t_from", "t_to", "time_from", "time_to",
             "anchor_time", "formed_at_time", "event_time", "t", "ref_time"}


def walk(a, b, path, report, check_times=True):
    """مقارنة عميقة. فروق الأزمنة تُسجل في فئة خاصة (0 → صحيح = إصلاح)."""
    if type(a) != type(b) and not (a is None and b is None):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a == b:
            return
        report["type_diff"].append((path, str(type(a)), str(type(b))))
        return
    if isinstance(a, dict):
        for k in set(a.keys()) | set(b.keys()):
            if k not in a:
                report["only_new"].append((path + "." + str(k), b))
                continue
            if k not in b:
                report["only_old"].append((path + "." + str(k), a))
                continue
            walk(a[k], b[k], path + "." + str(k), report, check_times)
    elif isinstance(a, list):
        if len(a) != len(b):
            report["len_diff"].append((path, len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", report, check_times)
    else:
        if a == b:
            return
        # فرق زمني؟ (0 في القديم → صحيح في الجديد = الإصلاح)
        leaf = path.rsplit(".", 1)[-1].split("[")[0]
        if leaf in TIME_KEYS and a in (0, None) and isinstance(b, (int, float)) and b > 0:
            report["time_fixed"].append((path, a, b))
        else:
            report["value_diff"].append((path, a, b))


report = {"type_diff": [], "only_new": [], "only_old": [], "len_diff": [],
          "value_diff": [], "time_fixed": []}

for key in OLD.keys():
    sub = {"type_diff": [], "only_new": [], "only_old": [], "len_diff": [],
           "value_diff": [], "time_fixed": []}
    walk(OLD[key], NEW[key], key, sub)
    for k in report:
        report[k].extend(sub[k])
    print(f"{key}: value_diff={len(sub['value_diff'])} len_diff={len(sub['len_diff'])} "
          f"type_diff={len(sub['type_diff'])} only_old={len(sub['only_old'])} "
          f"only_new={len(sub['only_new'])} time_fixed={len(sub['time_fixed'])}")

print("\n=== SUMMARY ===")
print("فروق قيم (يجب صفر):", len(report["value_diff"]))
for p, a, b in report["value_diff"][:15]:
    print(f"  {p}: old={str(a)[:70]} -> new={str(b)[:70]}")
print("فروق أطوال:", len(report["len_diff"]))
for x in report["len_diff"][:10]:
    print("  ", x)
print("فروق أنواع:", len(report["type_diff"]))
for x in report["type_diff"][:10]:
    print("  ", x)
print("أزمنة مُصلحة (0→صحيح):", len(report["time_fixed"]))
for p, a, b in report["time_fixed"][:8]:
    print(f"  {p}: {a} -> {b}")
json.dump({k: len(v) for k, v in report.items()},
          open(os.path.join(ROOT, "ab_compare_summary.json"), "w"), indent=1)
